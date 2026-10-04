"""Generate per-device credentials; never embed a shared password in an image."""
import os
import secrets
from pathlib import Path


def initialize(config_dir: Path, state_dir: Path) -> None:
    marker = state_dir / "alpine-initialized"
    if marker.exists():
        return
    env = config_dir / "secrets.env"
    password = secrets.token_urlsafe(18)
    text = env.read_text()
    if "ADMIN_PASSWORD=change-me-now" in text:
        temp = env.with_suffix(".tmp")
        temp.write_text(text.replace("ADMIN_PASSWORD=change-me-now", f"ADMIN_PASSWORD={password}"))
        os.chmod(temp, 0o600)
        owner = env.stat()
        os.chown(temp, owner.st_uid, owner.st_gid)
        temp.replace(env)
    # Credentials remain in the private local file; never print them to logs.
    marker.touch(mode=0o600)


if __name__ == "__main__":
    initialize(Path("/etc/pi-bus-time-display"), Path("/var/lib/pi-bus-time-display"))
