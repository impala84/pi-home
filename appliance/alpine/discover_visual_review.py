"""Render deterministic native Discover screenshots in Alpine GTK/Xvfb."""
import html
import importlib.util
import os
import subprocess
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


OUTPUT = Path(os.environ.get("PI_HOME_SCREENSHOT_DIR", "/screenshots"))
ART = Path("/tmp/pi-home-visual-art")
OUTPUT.mkdir(parents=True, exist_ok=True)
ART.mkdir(parents=True, exist_ok=True)

source = Path("/opt/pi-home/native-display/pi_bus_native.py")
spec = importlib.util.spec_from_file_location("pi_home_native_visual", source)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def fixture_art(key, label):
    """Create distinct fake artwork without shipping or downloading media."""
    palette = ("4d478f", "315d78", "7a5637", "4c725d", "754461", "556b37", "75463b", "3f567e")
    colour = palette[sum(key.encode("utf-8")) % len(palette)]
    path = ART / f"{key}.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
        f'<rect width="512" height="512" fill="#{colour}"/>'
        '<circle cx="256" cy="218" r="130" fill="none" stroke="#f2eee8" stroke-width="18" opacity=".62"/>'
        '<circle cx="256" cy="218" r="30" fill="#f2eee8" opacity=".72"/>'
        f'<text x="256" y="420" text-anchor="middle" fill="#fff" font-family="sans-serif" font-size="34" font-weight="700">{html.escape(label[:22])}</text>'
        '</svg>',
        encoding="utf-8",
    )
    return path


def settle(rounds=40):
    context = native.GLib.MainContext.default()
    for _ in range(rounds):
        while context.pending():
            context.iteration(False)
        time.sleep(.01)


def capture(name):
    settle()
    subprocess.run(["import", "-silent", "-window", "root", str(OUTPUT / f"{name}.png")], check=True)


def item(title, artist, number, kind="album"):
    return {"title": title, "artist": artist, "kind": kind, "key": f"item-{number}", "id": f"mix-{number}", "artwork_key": f"art-{number}"}


Gtk.init()
screen_width = int(os.environ.get("PI_HOME_SCREEN_WIDTH", "1280"))
screen_height = int(os.environ.get("PI_HOME_SCREEN_HEIGHT", "720"))
window = Gtk.Window(default_width=screen_width, default_height=screen_height)
window.set_decorated(False)
window.set_resizable(False)
window.add_css_class("theme-roon")
provider = Gtk.CssProvider(); provider.load_from_data(native.CSS)
Gtk.StyleContext.add_provider_for_display(window.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
display = native.Display()
display.settings_data["display_theme"] = "roon"
page = display.build_roon()
window.set_child(page)
window.present()
settle()
display.window = window
display.adapt_display()
display.discovery_active = True
display.discovery_request = 1
display.set_roon_view("discover")
display.roon_clock.set_text("07:26")
display.zone.set_text("NAD M33")


def render(section, data):
    display.discovery_section = section
    display.discovery_mix = ""
    display.discovery_signature = None
    for name, button in display.discover_tabs.items():
        if name == section: button.add_css_class("active")
        else: button.remove_css_class("active")
    display.render_discover(display.discovery_request, data)
    settle()
    for artwork_key, pictures in display.discovery_pictures.items():
        label = artwork_key.removeprefix("discover:").replace("art-", "COVER ")
        path = fixture_art(artwork_key.replace(":", "-"), label)
        for picture in pictures:
            picture.set_filename(str(path))
    settle()


recent = [
    item("Jah Victory", "Alpha Blondy", 1),
    item("Heyday", "The Church", 2),
    item("Mickey Mouse Operation", "Little People", 3),
    item("Chrysalis", "Emancipator", 4),
    item("Tsunami Sea", "Spiritbox", 5),
    item("Greyview", "Invent Animate", 6),
    item("Astro Lounge", "Smash Mouth", 7),
    item("Collected Reworks", "Foals", 8),
]
render("recent", {"status": "ready", "items": recent})
capture("recent-listened")

releases = [
    item("Happiness Anytime", "Leon Bridges", 11),
    item("Freedom Call: Sextet – Unity", "Dave Holland", 12),
    item("Aurora (Deluxe Edition)", "Yes", 13),
    item("Freedom Call: Prism – Freedom", "Dave Holland", 14),
    item("Freedom Call: Quintet – Synergism", "Dave Holland", 15),
    item("Utility Modern", "Brandon Seabrook / Bill Frisell / Rahsaan Carter / Marcus Gilmore", 16),
    item("fabric presents Max Cooper", "Max Cooper", 17),
    item("Sad Wings of Destiny (50th Anniversary Remixed & Remastered)", "Judas Priest", 18),
]
render("releases", {"status": "ready", "items": releases})
capture("new-releases")

mixes = [
    item("Coheed and Cambria Mix", "Coheed and Cambria", 21, "mix"),
    item("The Beatles Mix", "The Beatles", 22, "mix"),
    item("+44 Mix", "+44", 23, "mix"),
    item("Stray From the Path Mix", "Stray From the Path", 24, "mix"),
    item("The Band Mix", "The Band", 25, "mix"),
]
recommendations = [
    item("Painkiller", "Judas Priest", 31),
    item("British Steel", "Judas Priest", 32),
    item("Screaming for Vengeance", "Judas Priest", 33),
    item("Defenders of the Faith", "Judas Priest", 34),
    item("Firepower", "Judas Priest", 35),
]
daily = {
    "status": "ready",
    "items": mixes,
    "groups": [{
        "reason": "recent",
        "seed": item("Sad Wings of Destiny (50th Anniversary Remixed & Remastered)", "Judas Priest", 30),
        "items": recommendations,
    }],
}
render("daily", daily)
capture("daily-mixes")
for_you = display.discovery_daily_sections["recommendations"]
vertical = display.discovery_scroll.get_vadjustment()
vertical.set_value(max(vertical.get_lower(), min(vertical.get_upper() - vertical.get_page_size(), for_you.get_allocation().y - 42)))
capture("daily-for-you")
horizontal = for_you.get_hadjustment()
horizontal.set_value(min(horizontal.get_upper() - horizontal.get_page_size(), 240))
capture("daily-for-you-scrolled")

# Check actual allocated portrait geometry, not just requested widget sizes.
if screen_height > screen_width:
    assert display.roon_clock.compute_bounds(page)[1].get_y() + display.roon_clock.get_height() <= display.discover_subnav.compute_bounds(page)[1].get_y()
    assert display.discovery_sidebar.get_height() < 100
    assert display.discovery_scroll.get_height() > screen_height * .6
    first = display.discovery_cards[0][0]
    assert first.get_width() > screen_width * .3

display.discovery_active = True
display.discovery_section = "browse"
display.set_roon_view("browse")
for name, button in display.discover_tabs.items():
    (button.add_css_class if name == "browse" else button.remove_css_class)("active")
def browse_fixture(section, labels):
    display.render_browser({"status": "ready", "section": section, "layout": "covers", "show_labels": labels, "alpha_scrub": True, "items": [{"title": value["title"] + (" and a particularly long artist name" if labels else ""), "subtitle": value["artist"], "item_key": value["key"], "image_key": value["artwork_key"]} for value in recent * 3]})
    for key, pictures in display.browser_pictures.items():
        for picture in pictures: picture.set_filename(str(fixture_art(key, "LOADED COVER")))
    settle()
    assert window.get_width() == screen_width, (section, window.get_width(), screen_width)
    clock = display.roon_clock.compute_bounds(page)[1]
    assert clock.get_x() + clock.get_width() <= screen_width
    scrub = display.browser_scrubber.compute_bounds(page)[1]
    assert scrub.get_x() >= 0 and scrub.get_x() + scrub.get_width() <= screen_width - 4
browse_fixture("albums", False)
settle()
capture("browse")
if screen_height > screen_width:
    assert display.browser_sidebar.get_height() < 100
    assert display.browser_scroll.get_height() > screen_height * .6
    assert display.browser_grid_metrics()[0] == 3
browse_fixture("artists", True)
capture("browse-artists")

display.render_browser({"status": "ready", "section": "albums", "layout": "covers", "surprise_preview": True, "items": [{"title": "Based on a True Story", "subtitle": "Fat Freddy's Drop", "item_key": "surprise", "image_key": "surprise-art"}]})
for picture in display.browser_pictures.get("surprise-art", []): picture.set_filename(str(fixture_art("surprise-art", "SURPRISE")))
capture("surprise")
assert window.get_width() == screen_width and window.get_height() == screen_height
if screen_height > screen_width:
    stage = display.browser_list.get_first_child().get_first_child()
    assert stage.get_orientation() == Gtk.Orientation.VERTICAL

# Entering Recent resets Added, while its explicit Listened choice still works.
display.request_discovery = lambda *args: False
display.set_mode = lambda *args: None
display.open_recent("listened")
assert display.discovery_recent_mode == "listened"
display.open_discover("recent")
assert display.discovery_recent_mode == "added"

display.set_roon_view("now")
display.title.set_text("Solarium"); display.artist.set_text("Emancipator")
display.library_status = "in_library"; display.library_add.set_visible(True); display.set_library_icon(False)
display.artwork.set_filename(str(fixture_art("now-playing", "NOW PLAYING")))
display.render_bluos_inputs({"inputs": [{"id": "tv", "name": "Watch TV"}, {"id": "rega", "name": "Rega P3"}]}, True)
display.adapt_display()
capture("now-playing")
assert window.get_width() == screen_width and window.get_height() == screen_height, (window.get_width(), window.get_height(), screen_width, screen_height)
footer_bounds = page.get_last_child().compute_bounds(page)[1]
assert footer_bounds.get_y() + footer_bounds.get_height() <= screen_height - 4
if screen_height > screen_width: assert display.artwork.get_width() == display.artwork.get_height()

bus = display.build_bus(); window.set_child(bus)
display.render_bus({"status": "ok", "stop_name": "Flamingo Valley", "stop_code": "83249", "services": [{"service": number, "arrivals": [{"minutes": value, "monitored": True} for value in (1, 14, 28)]} for number in ("40", "42")]})
capture("bus-times")
if screen_height > screen_width:
    assert display.services.get_first_child().get_orientation() == Gtk.Orientation.VERTICAL
    assert not display.services.get_first_child().get_vexpand()
assert window.get_width() == screen_width and window.get_height() == screen_height
display.render_bus({"status": "ok", "stop_name": "Flamingo Valley", "stop_code": "83249", "services": [{"service": number, "arrivals": [{"minutes": value} for value in (1, 14, 28)]} for number in ("40", "42", "401", "14")]})
capture("bus-times-four-routes")
assert window.get_width() == screen_width and window.get_height() == screen_height

home = display.build_home(); window.set_child(home)
display.settings_data["display_theme"] = "roon"
display.render_home({"status": "ok", "entities": [{"entity_id": f"{domain}.fixture{index}", "domain": domain, "name": name, "state": "on", "supports_level": domain in ("fan", "light"), "percentage": 50} for index, (domain, name) in enumerate((("fan", "Living Room Fan"), ("light", "Living Room"), ("switch", "Pi-Hole Master"), ("switch", "Pi-Hole Slave")))]})
capture("home")
if screen_height > screen_width:
    assert display.home_grid.get_first_child().get_orientation() == Gtk.Orientation.HORIZONTAL

window.set_child(None)
display.root_overlay = Gtk.Overlay(); display.root_overlay.set_child(home); window.set_child(display.root_overlay)
display.confirm_reboot()
capture("reboot-confirmation")
card = display.reboot_confirmation.get_last_child()
bounds = card.compute_bounds(display.root_overlay)[1]
assert bounds.get_y() + bounds.get_height() / 2 < screen_height / 2 - 10

print(f"Wrote native Alpine visual review frames to {OUTPUT}")
