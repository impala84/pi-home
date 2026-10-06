"""Shared Netdata configuration and validated Cloud command parsing."""
import os
import re
import secrets
import shlex
from pathlib import Path


def configure_netdata_lightweight(root, enabled):
    """Manage the lightweight profile; preserve Cloud, alerts and storage."""
    if type(enabled) is not bool:
        raise ValueError("Choose a supported Netdata monitoring mode.")
    root = Path(root)
    directory = root / ("opt/netdata/etc/netdata" if (root / "opt/netdata/bin/netdata").is_file() else "etc/netdata")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "netdata.conf"
    text = read(path) if path.exists() else ""
    backup = directory / "netdata.conf.pi-home-backup"
    if not backup.exists(): atomic(backup, text, 0o640)
    settings = [("ml", "enabled", "no" if enabled else "auto"), ("db", "update every", "3" if enabled else "1")]
    original_plugins = re.search(r"(?ms)^\[plugins\][^\n]*\n(.*?)(?=^\[|\Z)", read(backup))
    for key in ("netflow", "otel", "scripts.d", "nfacct", "network-viewer", "debugfs", "apps", "go.d"):
        previous = re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(.*)$", original_plugins.group(1)) if original_plugins else None
        value = ("yes" if key in {"apps", "go.d"} else "no") if enabled else (previous.group(1) if previous else None)
        settings.append(("plugins", key, value))
    for section, key, value in settings:
        pattern = rf"(?ms)^\[{section}\][^\n]*\n(.*?)(?=^\[|\Z)"
        match = re.search(pattern, text)
        setting = f"    {key} = {value}\n" if value is not None else ""
        if match:
            body = re.sub(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=.*\n?", "", match.group(1))
            body = body.rstrip()
            text = text[:match.start(1)] + (body + "\n" if body else "") + setting + text[match.end(1):]
        elif value is not None:
            text = text.rstrip() + f"\n\n[{section}]\n" + setting
    atomic(path, text, 0o644)
    (root / "var/lib/pi-home").mkdir(parents=True, exist_ok=True)
    atomic(root / "var/lib/pi-home/netdata-lightweight", "yes\n" if enabled else "no\n")

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


def parse_netdata_connection_command(value):
    """Extract credentials from Netdata's generated command without running it."""
    value = str(value or "").strip()
    if not 20 <= len(value) <= 16_384 or "\x00" in value:
        raise ValueError("Paste the complete connection command from Netdata Cloud.")
    if "https://get.netdata.cloud/kickstart.sh" not in value:
        raise ValueError("Use the official Netdata Cloud connection command.")
    try:
        words = shlex.split(value)
    except ValueError as error:
        raise ValueError("The Netdata Cloud command could not be read. Copy it again in full.") from error
    options = {}
    for index, word in enumerate(words):
        for name in ("claim-token", "claim-rooms", "claim-url"):
            flag = "--" + name
            if word == flag and index + 1 < len(words): options[name] = words[index + 1]
            elif word.startswith(flag + "="): options[name] = word[len(flag) + 1:]
    token = str(options.get("claim-token", "")).strip()
    rooms = str(options.get("claim-rooms", "")).strip()
    url = str(options.get("claim-url", "https://app.netdata.cloud")).strip().rstrip("/")
    if not 8 <= len(token) <= 512 or any(character.isspace() or ord(character) < 33 for character in token):
        raise ValueError("The pasted command does not contain a valid claim token.")
    room_values = [room.strip() for room in rooms.split(",") if room.strip()]
    if any(not re.fullmatch(r"[A-Za-z0-9._:-]{4,128}", room) for room in room_values):
        raise ValueError("The pasted command contains an invalid Netdata Room ID.")
    if url != "https://app.netdata.cloud":
        raise ValueError("Only the official Netdata Cloud service is supported.")
    return token, ",".join(room_values), url
