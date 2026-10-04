"""Real HTTP -> unprivileged API -> private root helper -> bounded updater.

The updater executable is replaced only inside this disposable test container.
No network download or installed-device mutation happens in this test.
"""
import json
import os
from pathlib import Path
import pwd
import subprocess
import time
import urllib.error
import urllib.request

processes = []
root = Path("/opt/pi-home")
progress = Path("/var/lib/pi-home-setup/progress.json")
progress.parent.mkdir(mode=0o700, exist_ok=True)
progress.write_text('{"complete":true}'); progress.chmod(0o600)
worker = Path("/usr/local/sbin/pi-home-alpine-update")
worker.write_text('#!/usr/bin/env python3\nimport os\nfrom pathlib import Path\nPath("/tmp/update-button-uid").write_text(str(os.geteuid()))\n')
worker.chmod(0o755)
account = pwd.getpwnam("morningbus")
try:
    processes.append(subprocess.Popen(["python3", str(root / "appliance/alpine/setup_service.py")]))
    for _ in range(50):
        if Path("/run/pi-home-setup.sock").exists(): break
        time.sleep(.1)
    processes.append(subprocess.Popen([str(root / ".venv/bin/pi-home"), "--config", "/etc/pi-home/config.toml", "--env", "/etc/pi-home/secrets.env", "--state-dir", "/var/lib/pi-home", "--host", "127.0.0.1"], user=account.pw_uid, group=account.pw_gid, env={**os.environ, "PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}))
    request = urllib.request.Request("http://127.0.0.1:8765/api/device/update", data=b"{}", headers={"Content-Type": "application/json"})
    for attempt in range(50):
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                assert response.status == 202 and json.load(response)["queued"]
            break
        except urllib.error.URLError:
            if attempt == 49: raise
            time.sleep(.1)
    for _ in range(50):
        if Path("/tmp/update-button-uid").exists(): break
        time.sleep(.1)
    assert Path("/tmp/update-button-uid").read_text() == "0"
    print("Real update button HTTP/private-socket privilege boundary passed; updater action replaced with a harmless UID recorder.")
finally:
    for process in processes: process.terminate()
    for process in processes: process.wait(timeout=5)
