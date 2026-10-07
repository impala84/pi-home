"""GTK adapter for the canonical SVG family, with CSS colour/state inheritance.

Render the original vector, not GTK symbolic masks (which can fill outline holes).
"""
from pathlib import Path
from gi.repository import Gdk, GLib, Gtk

ASSETS = Path(__file__).resolve().parents[1] / 'roon-controller/static/icons'
ALIASES = {
    'media-playback-start-symbolic': 'play', 'media-playback-pause-symbolic': 'pause',
    'media-skip-backward-symbolic': 'previous', 'media-skip-forward-symbolic': 'next',
    'list-add-symbolic': 'add', 'view-list-symbolic': 'playlist',
    'media-playlist-shuffle-symbolic': 'shuffle', 'go-jump-symbolic': 'next',
    'view-refresh-symbolic': 'refresh', 'folder-music-symbolic': 'folder',
    'avatar-default-symbolic': 'artist', 'media-optical-symbolic': 'album',
    'audio-x-generic-symbolic': 'music', 'folder-symbolic': 'folder',
}

class FamilyIcon(Gtk.Image):
    _textures = {}

    def __init__(self, name, size=34, filled=False):
        super().__init__()
        self.icon_name = ALIASES.get(name, name)
        self.filled = filled
        self._colour = None
        self.set_pixel_size(size)
        self._refresh('#817aeb')

    def _refresh(self, colour):
        key = (self.icon_name, colour, self.filled)
        if key not in self._textures:
            path = ASSETS / (self.icon_name + '-symbolic.svg')
            if not path.exists(): path = ASSETS / 'music-symbolic.svg'
            svg = path.read_text().replace('currentColor', colour)
            if self.filled: svg = svg.replace('fill="none"', 'fill="' + colour + '"', 1)
            self._textures[key] = Gdk.Texture.new_from_bytes(GLib.Bytes.new(svg.encode()))
        self.set_from_paintable(self._textures[key])
        self._colour = colour

    def do_snapshot(self, snapshot):
        colour = self.get_style_context().get_color().to_string()
        if colour != self._colour: self._refresh(colour)
        Gtk.Image.do_snapshot(self, snapshot)
