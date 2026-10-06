"""Create a transparent Xcursor theme for the dedicated touchscreen session."""
from pathlib import Path
import struct


def prepare(base=Path("/run/pi-home/cursors")):
    theme = base / "pi-home-touch"
    cursors = theme / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    (theme / "index.theme").write_text("[Icon Theme]\nName=Pi Home Touch\n")
    # Xcursor file header, one image TOC, one 1×1 fully transparent ARGB image.
    data = struct.pack("<4I", 0x72756358, 16, 0x10000, 1)
    data += struct.pack("<3I", 0xfffd0002, 24, 28)
    data += struct.pack("<9I", 36, 0xfffd0002, 24, 1, 1, 1, 0, 0, 0)
    data += struct.pack("<I", 0)
    for name in ("left_ptr", "default", "arrow", "pointer", "hand2", "text", "xterm", "crosshair", "wait", "watch", "grabbing", "grab", "sb_h_double_arrow", "sb_v_double_arrow"):
        (cursors / name).write_bytes(data)
    return theme


if __name__ == "__main__": prepare()
