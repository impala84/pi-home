"""Bind the built-in Goodix touchscreen to its DSI output before Cage starts.

wlroots rotates absolute input only when it is mapped to an output. Do not
also apply a libinput calibration matrix or Device Tree input rotation.
"""
from pathlib import Path
import re
import subprocess
import time
from setup_service import atomic


def connected_output(root):
    outputs = set()
    for status in (root / "sys/class/drm").glob("card*-DSI-*/status"):
        if status.read_text().strip() == "connected":
            match = re.fullmatch(r"card\d+-(DSI-\d+)", status.parent.name)
            if match: outputs.add(match[1])
    return next(iter(outputs)) if len(outputs) == 1 else None


def mapping_rule(output):
    if not re.fullmatch(r"DSI-\d+", output): raise ValueError("Invalid DSI output")
    return ('# Pi Home: one rotation owner, the mapped Cage output.\n'
            'ACTION!="remove", SUBSYSTEM=="input", KERNEL=="event*", '
            'ENV{ID_INPUT_TOUCHSCREEN}=="1", ATTRS{name}=="Goodix Capacitive TouchScreen", '
            f'ENV{{WL_OUTPUT}}="{output}", ENV{{LIBINPUT_CALIBRATION_MATRIX}}="1 0 0 0 1 0"\n')


def main():
    root = Path("/")
    output = None
    for _ in range(30):
        output = connected_output(root)
        if output: break
        time.sleep(.1)
    rules = root / "etc/udev/rules.d/99-pi-home-dsi-touch.rules"
    rules.parent.mkdir(parents=True, exist_ok=True)
    atomic(rules, mapping_rule(output) if output else "# No single connected DSI output; leave external touch devices unchanged.\n")
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True, timeout=10)
    subprocess.run(["udevadm", "trigger", "--subsystem-match=input", "--action=change"], check=True, timeout=10)
    subprocess.run(["udevadm", "settle", "--timeout=10"], check=True, timeout=15)
    print(f"Pi Home touch mapping: Goodix -> {output}" if output else "Pi Home touch mapping: no unambiguous DSI output")


if __name__ == "__main__": main()
