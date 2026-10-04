"""Container HTTP/runtime verification, not Raspberry Pi boot verification."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_foreign("cairo")
from gi.repository import Gtk, Graphene  # noqa: F401

ROOT = Path("/opt/pi-home")
processes = []


def get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        assert response.status == 200
        return json.load(response)


try:
    processes.append(subprocess.Popen([
        str(ROOT / ".venv/bin/pi-home"),
        "--config", "/etc/pi-home/config.toml",
        "--env", "/etc/pi-home/secrets.env",
        "--state-dir", "/var/lib/pi-home", "--host", "127.0.0.1",
    ], env={**os.environ, "PI_HOME_APPLIANCE_PLATFORM": "alpine-prototype"}))
    processes.append(subprocess.Popen(["node", str(ROOT / "roon-controller/server.js")], cwd="/var/lib/pi-home/roon"))
    for port, path in ((8765, "/api/status"), (8766, "/api/state")):
        for attempt in range(30):
            assert all(p.poll() is None for p in processes), "A runtime exited"
            try:
                get(port, path)
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 29:
                    raise
                time.sleep(0.2)
    request = urllib.request.Request("http://127.0.0.1:8765/api/device/brightness", data=b"{}", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=2)
        raise AssertionError("Unsupported update was accepted")
    except urllib.error.HTTPError as error:
        assert error.code == 501
        assert "unavailable" in json.load(error)["error"]
    assert not Path("/var/lib/pi-home/system-action-queue").exists()
    print("Alpine ARM64: GTK/Cairo imports and both HTTP services passed; unsupported OS controls rejected.")
finally:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
