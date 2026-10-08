"""Check actual GTK snapshot pixels; no Pi hardware or instrument claim."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'native-display'))
from white_balance import create_display_window, IDENTITY
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

Gtk.init()
for gains, expected in [(IDENTITY, (255,255,255)), ((.9665,.8712,1), (246,222,255)), ((.8,.9,1), (204,230,255))]:
    window = create_display_window(gains=gains)
    window.set_decorated(False)
    window.set_default_size(64,64)
    area = Gtk.DrawingArea()
    def draw(area, cr, width, height):
        cr.set_source_rgb(1,1,1); cr.paint()
    area.set_draw_func(draw)
    window.set_child(area); window.present()
    for _ in range(40):
        while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
        time.sleep(.01)
    with tempfile.TemporaryDirectory() as folder:
        image = str(Path(folder) / 'white.png')
        subprocess.run(['import','-silent','-window','root',image],check=True)
        pixel = subprocess.check_output(['convert',image,'-format','%[pixel:p{32,32}]','info:'],text=True)
        values = [float(value) for value in re.findall(r'\d+(?:\.\d+)?',pixel)]
        if '%' in pixel: values = [value * 255 / 100 for value in values]
        if pixel.startswith('gray('): values = values * 3
        rgb = tuple(round(value) for value in values[:3])
        assert len(rgb) == 3 and all(abs(a-b) <= 1 for a,b in zip(rgb,expected)), (pixel,expected)
    window.destroy()
print('GTK white-balance identity and measured-gain pixels passed')
