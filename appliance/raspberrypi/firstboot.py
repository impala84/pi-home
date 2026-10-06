#!/usr/bin/env python3
"""Idempotent provisioning; leave SSH and application available on failure."""
import importlib.util
import os
from pathlib import Path
import pwd
import secrets
import uuid

APP = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, APP / "alpine" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def initialize(config, state, expand):
    marker = state / "raspberrypi-initialized"
    if marker.exists():
        return
    state.mkdir(parents=True, exist_ok=True)
    identity = state / "machine-id"
    if not identity.exists():
        identity.write_text(str(uuid.uuid4()) + "\n")
        identity.chmod(0o600)
    env = config / "secrets.env"
    content = env.read_text()
    if "ADMIN_PASSWORD=change-me-now" in content:
        temporary = env.with_suffix(".tmp")
        temporary.write_text(content.replace("ADMIN_PASSWORD=change-me-now", "ADMIN_PASSWORD=" + secrets.token_urlsafe(24)))
        temporary.chmod(0o600)
        owner = env.stat()
        os.chown(temporary, owner.st_uid, owner.st_gid)
        temporary.replace(env)
    # Credentials are safe even if storage expansion fails and the UI stays up.
    # Validate the actual mounted filesystem, not a guessed mmc device.
    expand()
    marker.write_text("complete\n")
    marker.chmod(0o600)


def main():
    state = Path("/var/lib/pi-home")
    try:
        storage = load("expand_root")
        initialize(Path("/etc/pi-home"), state, storage.expand)
        owner = pwd.getpwnam("morningbus")
        for path in (state / "machine-id", state / "raspberrypi-initialized"):
            os.chown(path, owner.pw_uid, owner.pw_gid)
    except Exception as error:
        print("Pi Home first boot needs attention: " + str(error), flush=True)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
