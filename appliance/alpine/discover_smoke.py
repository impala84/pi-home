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
horizontal, vertical = display.discovery_scroll.get_policy()
assert horizontal == Gtk.PolicyType.NEVER and vertical == Gtk.PolicyType.AUTOMATIC
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
scroller = display.discovery_list.get_first_child()
assert isinstance(scroller, Gtk.ScrolledWindow)
track = scroller.get_child()
if not isinstance(track, Gtk.Box): track = track.get_child()
assert isinstance(track, Gtk.Box)
cards=[]; child=track.get_first_child()
while child: cards.append(child); child=child.get_next_sibling()
assert len(cards) == 5
first = cards[0]
assert first.has_css_class("daily-card")
requested_width, requested_height = first.get_size_request()
assert requested_width > 0 and requested_height > 0
art = first.get_child().get_first_child()
assert isinstance(art, Gtk.ScrolledWindow)
assert art.get_min_content_width() == art.get_max_content_width()
assert art.get_min_content_height() == art.get_max_content_height()
horizontal, vertical = scroller.get_policy()
assert horizontal == Gtk.PolicyType.AUTOMATIC and vertical == Gtk.PolicyType.NEVER
recommendations = scroller.get_next_sibling()
assert isinstance(recommendations, Gtk.ScrolledWindow)
recommendation_track = recommendations.get_child()
if not isinstance(recommendation_track, Gtk.Box): recommendation_track = recommendation_track.get_child()
context = recommendation_track.get_first_child()
assert context.has_css_class("recommendation-card")
reason = context.get_first_child().get_next_sibling()
seed = reason.get_next_sibling()
assert reason.get_text() == "Because you listened to"
assert seed.get_text() == "Altered State"
assert display.discovery_daily_sections.keys() == {"mixes", "recommendations"}
assert display.discovery_daily_sections["mixes"] is scroller
display.browser_sidebar.set_visible(True)
display.browser_list.append(display.label("Stale Browse content"))
requests = []
display.request_browser = lambda action, **_payload: requests.append(action)
display.set_mode = lambda _mode: None
display.open_discover("surprise")
assert requests == ["surprise"]
assert not display.browser_sidebar.get_visible()
assert display.browser_list.get_first_child().get_text() == "Loading…"
display.root_overlay = Gtk.Overlay(); display.root_overlay.set_child(Gtk.Box())
display.device_status = display.label("")
display.confirm_reboot()
shade = display.reboot_confirmation
assert isinstance(shade, Gtk.Overlay)
card = shade.get_last_child()
assert card.get_halign() == Gtk.Align.CENTER and card.get_valign() == Gtk.Align.CENTER
print("Native Alpine GTK Discover has working touch scrollers, fixed cards, a clean Surprise transition and a centred restart panel.")
