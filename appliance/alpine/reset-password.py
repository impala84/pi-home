#!/usr/bin/env python3
"""Root-only interactive web-password recovery; never echo credentials."""
import getpass
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, "/opt/pi-home/appliance/alpine")
from setup_service import atomic, command, read, validate_password


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run sudo pi-home-reset-password from your SSH session.")
    password = getpass.getpass("New web settings password: ")
    validate_password(password)
    if password != getpass.getpass("Enter it again: "):
        raise ValueError("Passwords do not match. Nothing changed.")
    path = Path("/etc/pi-home/secrets.env")
    text, count = re.subn(r"^ADMIN_PASSWORD=.*$", lambda _: "ADMIN_PASSWORD=" + password, read(path), flags=re.M)
    if count != 1: raise ValueError("Password configuration needs repair; nothing changed.")
    atomic(path, text, 0o600)
    command(["rc-service", "pi-home-api", "restart"])
    print("Web password reset. SSH password unchanged. Sign in as admin.")


if __name__ == "__main__":
    try: main()
    except ValueError as error: raise SystemExit(str(error))
