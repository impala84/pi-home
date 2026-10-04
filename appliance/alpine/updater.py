#!/usr/bin/env python3
"""Alpine application updates: verified prototype revisions, staged and reversible.

No kernel/APK upgrades, no setup re-run, and no user-supplied download URLs.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import time
import urllib.request

APP = Path("/opt/pi-home")
STATE = Path("/var/lib/pi-home")
REPO = "https://api.github.com/repos/impala84/pi-home"
BRANCH = "alpine-appliance-prototype"


def status(message):
    temporary = STATE / ".alpine-update-status"
    temporary.write_text(message + "\n"); temporary.chmod(0o644)
    temporary.replace(STATE / "update-status")
    print(message, flush=True)


def run(args, timeout=300):
    # Keep dependency output in a private local log, never in HTTP responses.
    # Streaming to disk also shows progress while pip/npm are still running.
    log = STATE / "update.log"
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as file:
        os.fchmod(file.fileno(), 0o600)
        file.write(f"\n{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} Starting {Path(args[0]).name}\n"); file.flush()
        try:
            result = subprocess.run(args, stdout=file, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            file.write("Step timed out\n"); file.flush()
            raise RuntimeError("Application preparation timed out; see the private update log")
        file.write(f"Step finished with exit status {result.returncode}\n")
    if result.returncode: raise RuntimeError("Application preparation or service restart failed; see the private update log")


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Pi-Home-Alpine-Updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response: return json.load(response)


def verified_revision():
    result = fetch_json(REPO + "/actions/workflows/alpine-image.yml/runs?branch=" + BRANCH + "&status=success&per_page=1")
    runs = result.get("workflow_runs", [])
    if not runs: raise RuntimeError("No verified Alpine build is available")
    build = runs[0]; sha = build.get("head_sha", "")
    if build.get("head_branch") != BRANCH or build.get("conclusion") != "success" or build.get("event") not in {"push", "workflow_dispatch"} or build.get("head_repository", {}).get("full_name") != "impala84/pi-home" or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Invalid verified build response")
    return sha


def extract_source(archive, destination):
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 10000: raise RuntimeError("Too many source files")
        if sum(item.size for item in members) > 100_000_000: raise RuntimeError("Source package is too large")
        for item in members:
            parts = Path(item.name).parts
            if not parts or item.name.startswith("/") or ".." in parts or not (item.isfile() or item.isdir()):
                raise RuntimeError("Unsafe source package")
        tar.extractall(destination, filter="data")
    roots = list(destination.iterdir())
    if len(roots) != 1 or not (roots[0] / "appliance/alpine/updater.py").is_file():
        raise RuntimeError("Not an Alpine-compatible application package")
    return roots[0]


def activate(target):
    temporary = APP.with_name(".pi-home-next")
    if temporary.is_symlink(): temporary.unlink()
    temporary.symlink_to(target)
    temporary.replace(APP)


def healthy():
    for _ in range(30):
        try:
            for url in ("http://127.0.0.1:8765/api/status", "http://127.0.0.1:8766/api/state"):
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status != 200: raise OSError("Not ready")
            run(["rc-service", "pi-home-display", "status"], timeout=10)
            return True
        except (OSError, RuntimeError, subprocess.TimeoutExpired): time.sleep(1)
    return False


def restart():
    # OpenRC otherwise cycles dependent services during each backend restart.
    # Hold the display stopped until every backend has restarted so Cage/seatd
    # cannot race a second display start for the service/DRM locks.
    run(["rc-service", "--nodeps", "pi-home-display", "stop"], timeout=45)
    for service in ("pi-home-setup", "pi-home-api", "pi-home-roon"):
        run(["rc-service", "--nodeps", service, "restart"], timeout=45)
    run(["rc-service", "--nodeps", "pi-home-display", "start"], timeout=45)


def update():
    status("Update · Checking verified Alpine prototype builds…")
    sha = verified_revision()
    if (APP / ".source-commit").exists() and (APP / ".source-commit").read_text().strip() == sha:
        status("Update unchanged. Latest verified Alpine prototype is installed."); return
    releases = Path("/opt/pi-home-releases"); releases.mkdir(exist_ok=True, mode=0o755)
    if shutil.disk_usage(releases).free < 400_000_000:
        raise RuntimeError("Not enough free space to stage an update; current application unchanged")
    target = releases / (sha + "-" + str(time.time_ns()))
    # Stage dependencies while the existing app remains running.
    with tempfile.TemporaryDirectory(prefix="pi-home-source-") as folder:
        temporary = Path(folder); archive = temporary / "source.tar.gz"
        status("Update · Downloading verified application files…")
        url = "https://codeload.github.com/impala84/pi-home/tar.gz/" + sha
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as file:
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 30_000_000: raise RuntimeError("Source download is too large")
                file.write(chunk)
        source = extract_source(archive, temporary / "unpacked")
        source.rename(target)
    (target / ".source-commit").write_text(sha + "\n")
    status("Update · Creating Python environment…")
    run(["python3", "-m", "venv", "--system-site-packages", str(target / ".venv")])
    status("Update · Installing Pi Home Python package…")
    run([str(target / ".venv/bin/pip"), "install", "--no-build-isolation", "--no-deps", str(target)])
    status("Update · Downloading Roon dependencies…")
    run(["npm", "--prefix", str(target / "roon-controller"), "ci", "--omit=dev", "--no-audit", "--no-fund"])
    status("Update · Checking prepared application…")
    run([str(target / ".venv/bin/python"), "-c", "import gi; gi.require_version('Gtk', '4.0'); gi.require_foreign('cairo'); from pi_bus_time_display import __version__"])
    for path in ("native-display/pi_bus_native.py", "scripts/pi-bus-cage-launch", "appliance/alpine/display-session"):
        (target / path).chmod(0o755)
    previous = APP.resolve()
    if not APP.is_symlink():
        previous = releases / "initial-image"
        if previous.exists(): raise RuntimeError("Initial image backup already exists; repair required")
        APP.rename(previous)
    try:
        activate(target)
        shutil.copyfile(target / "appliance/alpine/display-launch", "/usr/local/bin/pi-home-display-launch")
        Path("/usr/local/bin/pi-home-display-launch").chmod(0o755)
        status("Update · Restarting and checking Pi Home…")
        restart()
        if not healthy(): raise RuntimeError("New application did not become healthy")
        status("Update installed. Alpine prototype " + sha[:7] + "; settings and pairing preserved.")
    except Exception as failure:
        activate(previous)
        shutil.copyfile(previous / "appliance/alpine/display-launch", "/usr/local/bin/pi-home-display-launch")
        Path("/usr/local/bin/pi-home-display-launch").chmod(0o755)
        restart()
        if not healthy(): raise RuntimeError("Update failed; previous files restored but services need attention")
        raise RuntimeError("Update failed; previous working application restored: " + str(failure)) from failure


def main():
    if os.geteuid() != 0: raise SystemExit("Run with sudo")
    with open("/run/pi-home-update.lock", "a") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        try: update()
        except Exception as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, ssl.SSLCertVerificationError):
                message = "HTTPS certificate check failed. Check the Pi clock and network time sync; existing installation retained"
            else:
                message = str(error) if isinstance(error, RuntimeError) else "Download or application preparation failed; existing installation retained"
            status("Failed: " + message)
            raise SystemExit(1)


if __name__ == "__main__": main()
