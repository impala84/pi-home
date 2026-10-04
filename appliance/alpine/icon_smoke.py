"""Load every shared SVG through Alpine's real GTK and SVG image loader."""
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GdkPixbuf

Gtk.init()
theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
paths = sorted(Path('/opt/pi-home/roon-controller/static/icons').glob('*-symbolic.svg'))
assert len(paths) == 18
for path in paths:
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 54, 54, True)
    assert pixbuf.get_width() == 54
    icon = Gio.FileIcon.new(Gio.File.new_for_path(str(path)))
    paintable = theme.lookup_by_gicon(icon, 54, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.FORCE_SYMBOLIC)
    assert paintable.is_symbolic(), path
    assert paintable.get_file().get_path() == str(path), path
    image = Gtk.Image.new_from_gicon(icon)
    image.set_pixel_size(54)
print('All 18 bundled SVG icons load and are symbolic on Alpine; no genre font glyphs required.')
