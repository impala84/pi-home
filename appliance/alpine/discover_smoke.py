"""Exercise the real native Discover widgets under Alpine GTK/Xvfb."""
import importlib.util
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

source = Path("/opt/pi-home/native-display/pi_bus_native.py")
spec = importlib.util.spec_from_file_location("pi_home_native", source)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

Gtk.init()
display = native.Display()
display.build_roon()

assert display.discover_tabs["daily"].get_label() == "DAILY"
display.discovery_section = "daily"
display.discovery_picks = True
navigation, selected = display.discovery_secondary_navigation()
assert navigation == (("mixes", "MIXES"), ("recommendations", "FOR YOU"))
assert selected == "mixes"

display.discovery_active = True
display.discovery_request = 1
display.roon_views.set_visible_child_name("discover")
items = [{"title": f"Mix {number}", "artist": "Artist", "kind": "mix"} for number in range(1, 6)]
groups = [{"reason":"recent","seed":{"title":"Altered State"},"items":items}]
assert display.render_discover(1, {"status": "ready", "items": items, "groups": groups}) is False
overlay = display.discovery_list.get_first_child()
assert isinstance(overlay, Gtk.Overlay)
scroller = overlay.get_child(); track = scroller.get_child()
assert isinstance(scroller, Gtk.ScrolledWindow) and isinstance(track, Gtk.Box)
cards=[]; child=track.get_first_child()
while child: cards.append(child); child=child.get_next_sibling()
assert len(cards) == 5
first = cards[0]
assert first.has_css_class("daily-card")
heading = overlay.get_next_sibling()
assert isinstance(heading, Gtk.Box) and heading.has_css_class("recommendation-heading")
assert heading.get_first_child().get_text() == "Because you listened to"
assert heading.get_last_child().get_text() == "Altered State"
assert display.discovery_daily_sections.keys() == {"mixes", "recommendations"}
print("Native Alpine GTK Discover shows a swipeable Daily feed with compact cards and split recommendation headings.")
