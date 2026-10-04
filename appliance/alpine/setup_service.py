"""Local-only, bounded first-boot actions. Never expose this helper over HTTP."""
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import struct
import subprocess
import threading
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SOCKET = "/run/pi-home-setup.sock"
PROFILES = {"auto": "", "original": "vc4-kms-dsi-7inch", "touch2-5": "vc4-kms-dsi-ili9881-5inch", "touch2-7": "vc4-kms-dsi-ili9881-7inch", "touch2-10": "vc4-kms-dsi-ili79600-10-1inch"}


def read(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW)) as file:
        return file.read()


def atomic(path, text, mode=0o644):
    path = Path(path)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8))
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as file:
        file.write(text)
        file.flush(); os.fsync(file.fileno())
    if path.exists() and not path.is_symlink():
        owner = path.stat()
        os.chown(temporary, owner.st_uid, owner.st_gid)
    temporary.replace(path)


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=45)
    if result.returncode:
        # Never return subprocess output: Wi-Fi/password commands may echo secrets.
        raise ValueError("Could not apply that setting. Check it and try again.")
    return result.stdout.strip()


def set_login_password(password):
    result = subprocess.run(["chpasswd"], input="admin:" + password + "\n", capture_output=True, text=True, timeout=15)
    if result.returncode: raise ValueError("Could not set the SSH password. Please retry.")


def validate_password(password):
    if not 8 <= len(password) <= 128 or any(c in password for c in "\r\n\x00"):
        raise ValueError("Choose a password of 8–128 characters.")
    if password != password.strip().strip("'\""):
        raise ValueError("Do not start or end the password with spaces or quotation marks.")


def display_power(root, powered, brightness_percent=100):
    """Control the backlight without disabling the DSI touch controller."""
    brightness_percent = int(brightness_percent)
    if not 10 <= brightness_percent <= 100: raise ValueError("Brightness must be between 10 and 100.")
    devices = sorted((Path(root) / "sys/class/backlight").glob("*"))
    devices = [device for device in devices if (device / "brightness").exists() or (device / "bl_power").exists()]
    if not devices: raise ValueError("No display backlight control was found.")
    for device in devices:
        brightness = device / "brightness"; power = device / "bl_power"
        if powered:
            if power.exists(): power.write_text("0", encoding="ascii")
            if brightness.exists():
                maximum = int((device / "max_brightness").read_text(encoding="ascii")) if (device / "max_brightness").exists() else 255
                brightness.write_text(str(max(1, round(maximum * brightness_percent / 100))), encoding="ascii")
        elif brightness.exists():
            # Brightness zero switches the backlight off while leaving Goodix
            # alive, so the next contact can still wake the application.
            brightness.write_text("0", encoding="ascii")
        elif power.exists():
            power.write_text("4", encoding="ascii")


class Setup:
    def __init__(self, root=Path("/"), run=command, roon=None, login_password=set_login_password):
        self.root = Path(root); self.run = run; self.roon = roon or self.roon_state
        self.login_password = login_password
        self.tools_lock = threading.Lock()
        self.progress = self.root / "var/lib/pi-home-setup/progress.json"
        self.progress.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def roon_state(self):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8766/api/state", timeout=3) as response:
                return json.load(response)
        except (OSError, ValueError):
            return {"connected": False, "zones": []}

    def saved(self):
        return json.loads(read(self.progress)) if self.progress.exists() else {}

    def save(self, state):
        atomic(self.progress, json.dumps(state), 0o600)

    def setting(self, key, value):
        path = self.root / "etc/pi-home/config.toml"
        text = read(path)
        replacement = f"{key} = {json.dumps(value)}"
        text, count = re.subn(rf"^{key}\s*=.*$", lambda _: replacement, text, flags=re.M)
        if count != 1: raise ValueError("Configuration needs repair before setup can continue.")
        atomic(path, text, 0o640)

    def connected(self):
        output = self.run(["nmcli", "-t", "-f", "STATE", "device"])
        return any(line == "connected" for line in output.splitlines())

    def handle(self, data):
        state = self.saved(); action = data.get("action")
        if action == "status":
            try: connected = self.connected()
            except (ValueError, subprocess.TimeoutExpired): connected = False
            return {"ok": True, "progress": state, "connected": connected, "roon": self.roon()}
        if action == "update":
            if not state.get("complete"): raise ValueError("Finish setup before updating.")
            atomic(self.root / "var/lib/pi-home/update-status", "Update · Queued…\n")
            subprocess.Popen(["/usr/bin/python3", "/opt/pi-home/appliance/alpine/updater.py"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return {"ok": True, "queued": True}
        if action == "install_tools":
            if not state.get("complete"): raise ValueError("Finish setup before installing tools.")
            if not self.tools_lock.acquire(blocking=False):
                return {"ok": True, "queued": False}
            atomic(self.root / "var/lib/pi-home/tools-status", "Installing system tools…\n")
            threading.Thread(target=self.install_tools, daemon=True).start()
            return {"ok": True, "queued": True}
        if action in {"display_on", "display_off", "set_brightness"}:
            if not state.get("complete"): raise ValueError("Finish setup before controlling the display.")
            display_power(self.root, action != "display_off", data.get("brightness", 100))
            return {"ok": True, "powered": action != "display_off"}
        if action in {"netdata_enable", "netdata_disable"}:
            if not state.get("complete"): raise ValueError("Finish setup before changing services.")
            if not (self.root / "etc/init.d/netdata").is_file():
                raise ValueError("Netdata is not installed. Install the Alpine netdata and netdata-openrc packages.")
            if action == "netdata_enable":
                self.run(["rc-update", "add", "netdata", "default"])
                self.run(["rc-service", "netdata", "start"])
            else:
                self.run(["rc-service", "netdata", "stop"])
                self.run(["rc-update", "del", "netdata", "default"])
            return {"ok": True}
        if action == "reboot" and (state.get("complete") or state.get("orientation")):
            threading.Timer(2, lambda: self.run(["/sbin/reboot"])).start()
            return {"ok": True}
        if state.get("complete"): raise ValueError("Setup is already complete.")
        if action == "name":
            name = str(data.get("hostname", "")).lower()
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", name):
                raise ValueError("Use 1–63 letters, numbers or hyphens; no spaces or edge hyphens.")
            self.run(["hostname", name]); atomic(self.root / "etc/hostname", name + "\n")
            self.run(["rc-service", "avahi-daemon", "restart"])
            state["hostname"] = name
        elif action == "wifi":
            ssid = str(data.get("ssid", "")); password = str(data.get("password", ""))
            if not ssid or len(ssid.encode()) > 32 or any(c in ssid + password for c in "\x00\r\n") or len(password) > 128:
                raise ValueError("Enter a valid Wi-Fi name and password.")
            args = ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
            if password: args += ["password", password]
            self.run(args)
            if not self.connected(): raise ValueError("Wi-Fi is not connected yet. Please try again.")
            state["network"] = True
        elif action == "network":
            if not self.connected(): raise ValueError("Connect Ethernet or Wi-Fi first.")
            state["network"] = True
        elif action == "roon":
            zone = str(data.get("zone", ""))
            if not data.get("skip"):
                if zone not in [z.get("name") for z in self.roon().get("zones", [])]:
                    raise ValueError("Authorise Pi Home in Roon, refresh, then choose an available zone.")
            else: zone = ""
            self.setting("roon_zone_name", zone); state["roon"] = True; state["zone"] = zone
        elif action in {"orientation", "display"}:
            profile = data.get("profile"); rotation = data.get("rotation")
            if not isinstance(profile, str) or not isinstance(rotation, str) or profile not in PROFILES or rotation not in {"normal", "90", "180", "270"}:
                raise ValueError("Choose a supported display and orientation.")
            if profile in {"auto", "original"} and rotation != "normal":
                raise ValueError("Use Normal for automatic/original displays in this prototype.")
            theme = data.get("theme", "roon"); timezone = data.get("timezone", "UTC")
            if theme not in ("roon", "fresh-mint") or not isinstance(timezone, str): raise ValueError("Choose a supported theme and timezone.")
            try: ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError): raise ValueError("Enter an IANA timezone, such as Europe/London or Asia/Singapore.")
            boot = self.root / "boot/config.txt"
            text = read(boot)
            text = re.sub(r"\n?# BEGIN PI HOME SETUP\n.*?# END PI HOME SETUP\n?", "\n", text, flags=re.S)
            if not Path(str(boot) + ".setup-backup").exists(): atomic(Path(str(boot) + ".setup-backup"), text)
            text = re.sub(r"^display_auto_detect=.*$", "display_auto_detect=" + ("1" if profile == "auto" else "0"), text, flags=re.M)
            overlay = PROFILES[profile]
            if overlay:
                if not (self.root / f"boot/overlays/{overlay}.dtbo").is_file(): raise ValueError("Display driver is missing from this image.")
                # Direct libinput calibration owns touch rotation. Do not add
                # kernel swaps/inversions or WL_OUTPUT mapping on top of it.
                text += f"\n# BEGIN PI HOME SETUP\n[all]\ndtoverlay={overlay}\n# END PI HOME SETUP\n"
            atomic(boot, text)
            config = self.root / "etc/pi-home"
            atomic(config / "display-profile", profile); atomic(config / "display-transform", rotation)
            state.update(orientation=True, profile=profile, rotation=rotation)
            if action == "display":
                self.setting("display_theme", theme); self.setting("timezone", timezone)
                state.update(display=True, theme=theme, timezone=timezone)
        elif action == "finish":
            if not all(state.get(key) for key in ("hostname", "network", "roon", "display")):
                raise ValueError("Complete the setup steps first.")
            password = str(data.get("password", ""))
            validate_password(password)
            if password != data.get("confirmation"):
                raise ValueError("The two passwords do not match. Please enter them again.")
            env = self.root / "etc/pi-home/secrets.env"
            text = re.sub(r"^ADMIN_PASSWORD=.*$", lambda _: "ADMIN_PASSWORD=" + password, read(env), flags=re.M)
            atomic(env, text, 0o600)
            self.login_password(password)
            if data.get("ssh", True):
                self.run(["rc-update", "add", "sshd", "default"])
                self.run(["rc-service", "sshd", "start"])
            else:
                self.run(["rc-update", "del", "sshd", "default"])
                self.run(["rc-service", "sshd", "stop"])
            state["ssh"] = bool(data.get("ssh", True))
            self.run(["rc-service", "pi-home-api", "restart"])
            state["complete"] = True
        else: raise ValueError("Unknown setup action.")
        self.save(state)
        return {"ok": True, "progress": state}


    def install_tools(self):
        path = self.root / "var/lib/pi-home/tools-status"
        try:
            # Fixed allowlist only: never accept package names from HTTP clients.
            result = subprocess.run(["apk", "add", "--no-cache", "grim", "procps", "netdata", "netdata-openrc", "chrony", "chrony-openrc"], capture_output=True, text=True, timeout=240)
            if result.returncode: raise ValueError("Installation failed. Check the network, clock and free disk space, then retry.")
            self.run(["rc-update", "add", "chronyd", "default"])
            self.run(["rc-service", "chronyd", "start"])
            launcher = self.root / "usr/local/bin/pi-home-display-launch"
            shutil.copyfile(Path(__file__).with_name("display-launch"), launcher)
            launcher.chmod(0o755)
            atomic(path, "System tools installed. Enable Netdata if wanted; reboot to apply the cursor theme.\n")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            atomic(path, "Installation failed. Check the network, clock and free disk space, then retry.\n")
        finally:
            self.tools_lock.release()


def serve():
    app = Setup(); uid = pwd.getpwnam("morningbus").pw_uid
    path = Path(SOCKET)
    if path.exists():
        if not path.is_socket(): raise RuntimeError("Unexpected setup socket path")
        path.unlink()
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(SOCKET); os.chmod(SOCKET, 0o600); os.chown(SOCKET, uid, -1); server.listen(4)
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(5)
                peer = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if peer[1] != uid: continue
                try:
                    message = connection.makefile("rb").readline(4097)
                    if len(message) > 4096: raise ValueError("Setup request is too large.")
                    data = json.loads(message)
                    if not isinstance(data, dict): raise ValueError("Invalid setup request.")
                    result = app.handle(data)
                except ValueError as error:
                    result = {"ok": False, "error": str(error)}
                except (TypeError, OSError, subprocess.TimeoutExpired):
                    result = {"ok": False, "error": "Could not apply this step. Check your settings and connection, then try again."}
                connection.sendall((json.dumps(result) + "\n").encode())


if __name__ == "__main__": serve()
