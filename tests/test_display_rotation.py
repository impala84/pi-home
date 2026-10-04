import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DisplayRotationTests(unittest.TestCase):
    def test_native_browse_is_vertical_only_and_back_is_not_an_overlay(self):
        display = (ROOT / "native-display/pi_bus_native.py").read_text()
        self.assertNotIn('browser.add_overlay(self.browser_back)', display)
        self.assertNotIn('browser_scroll.set_policy(Gtk.PolicyType.EXTERNAL', display)
        self.assertIn('previous_drag.connect("drag-end", self.browser_swipe_back)', display)
        self.assertIn('self.browser_artist_scroll.set_propagate_natural_height(False)', display)

    def test_native_bus_title_shares_clock_header_and_saves_a_row(self):
        display = (ROOT / "native-display/pi_bus_native.py").read_text()
        self.assertIn('page.append(self.header(stop_heading, self.bus_clock))', display)
        self.assertIn('stop_heading.append(self.stop_code)', display)
        self.assertNotIn('page.append(stop_row)', display)

    def test_system_uses_compact_accessible_tabs_instead_of_anchors(self):
        html = (ROOT / "src/pi_bus_time_display/static/admin.html").read_text()
        css = (ROOT / "src/pi_bus_time_display/static/admin.css").read_text()
        self.assertIn('class="system-tabs" aria-label="System settings" role="tablist"', html)
        self.assertEqual(html.count('data-system-panel='), 6)
        self.assertIn('aria-controls="system-web"', html)
        self.assertIn('data-system-anchor="system-web">Access</button>', html)
        self.assertIn('.system-tabs button[aria-selected="true"]', css)
        self.assertIn('.system-tab-panel>summary{display:none}', css)

    def test_bus_colours_are_keyed_by_route_not_row_position(self):
        css = (ROOT / "src/pi_bus_time_display/static/bus-refinements.css").read_text()
        self.assertNotIn(".service:nth-child", css)
        self.assertIn(".service.service-blue", css)
        self.assertIn(".service.service-green", css)
        self.assertIn(".service.service-violet", css)

    def test_touch_uses_inverse_wayland_quarter_turn(self):
        script = (ROOT / "scripts" / "pi-bus-appliance-mode").read_text(encoding="utf-8")
        self.assertIn("90) matrix='0 1 0 -1 0 1'", script)
        self.assertIn("270) matrix='0 -1 1 1 0 0'", script)

    def test_touch_rotation_is_not_applied_twice(self):
        script = (ROOT / "scripts" / "pi-bus-appliance-mode").read_text(encoding="utf-8")
        self.assertNotIn('ENV{WL_OUTPUT}', script)
        self.assertIn("[[ ${profile} == touch2-* ]] && matrix='1 0 0 0 1 0'", script)

    def test_touch_display_2_uses_supported_device_tree_rotation(self):
        script = (ROOT / "scripts" / "pi-bus-appliance-mode").read_text(encoding="utf-8")
        self.assertIn("90) flags=',swapxy,invx'", script)
        self.assertIn("180) flags=',invx,invy'", script)
        self.assertIn("270) flags=',swapxy,invy'", script)
        self.assertIn("vc4-kms-dsi-ili9881-7inch", script)
        self.assertIn('cmp -s "${boot_config}.tmp" "${boot_config}"', script)

    def test_goodix_multitouch_contact_can_wake_the_display(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        service = (ROOT / "systemd" / "pi-bus-native.service.in").read_text(encoding="utf-8")
        self.assertIn("event_type == 3 and code == 57", display)
        self.assertIn("value != 0xFFFFFFFF", display)
        self.assertIn("Environment=PYTHONUNBUFFERED=1", service)

    def test_sleep_button_touch_cannot_replay_as_a_wake(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        self.assertIn("GLib.idle_add(self.low_level_touch_wake, contact_at)", display)
        self.assertIn("self.last_interaction = max(self.last_interaction, contact_at or time.monotonic())", display)
        self.assertIn("contact_at <= self.sleep_entered_at", display)
        self.assertIn("self.inactivity_sleeping = True\n            self.prepare_sleep_wake()", display)
        self.assertIn("if self.manual_sleep_pending:", display)
        self.assertIn('target = "/sleep.html"', display)
        self.assertIn("for attempt in range(3):", display)

    def test_wayland_uses_inverse_quarter_turn(self):
        script = (ROOT / "scripts" / "pi-bus-cage-launch").read_text(encoding="utf-8")
        self.assertIn("90) transform=270", script)
        self.assertIn("270) transform=90", script)

    def test_landscape_profile_has_dedicated_large_touch_layout(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        self.assertIn('self.window.add_css_class("touch-landscape")', display)
        self.assertIn(".touch-landscape .settings-title", display)
        self.assertIn(".touch-landscape .roon-subnav button", display)
        self.assertIn('self.stack.add_named(self.build_boot_splash(), "boot")', display)
        self.assertIn('.boot-logo { color: #6ef0be', display)

    def test_landscape_artwork_is_fixed_smaller_and_detail_art_can_close(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        web_html = (ROOT / "roon-controller" / "static" / "index.html").read_text(encoding="utf-8")
        web_js = (ROOT / "roon-controller" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("self.artwork.set_size_request(324, 324)", display)
        self.assertIn("self.artwork_button.set_size_request(324, 324)", display)
        self.assertIn('detail_artwork_button.connect("clicked", lambda *_: self.set_roon_view("now"))', display)
        self.assertIn('id="details-artwork-close"', web_html)
        self.assertIn("$('details-artwork-close').onclick = () => setMusicView('now')", web_js)
        self.assertNotIn('id="details-close"', web_html)
        self.assertNotIn('"detail-back"', display)

    def test_touchscreen_settings_title_and_checkbox_spacing(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        self.assertIn('title = self.label("Settings", "settings-title", .5)', display)
        self.assertIn(".setting-line checkbutton label { margin-left: 12px;", display)

    def test_mobile_roon_navigation_uses_compact_uppercase_labels(self):
        app = (ROOT / "roon-controller" / "static" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "roon-controller" / "static" / "refinements.css").read_text(encoding="utf-8")
        self.assertIn("function compactLabel(label)", app)
        self.assertIn("words[words.length - 1]", app)
        self.assertIn(".nav-label-compact { display: inline; }", css)
        self.assertIn("text-transform: uppercase", css)

    def test_mobile_navigation_and_surprise_preview_layout(self):
        css = (ROOT / "roon-controller" / "static" / "refinements.css").read_text(encoding="utf-8")
        app = (ROOT / "roon-controller" / "static" / "app.js").read_text(encoding="utf-8")
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        self.assertNotIn("#browser-surprise { font-size:", css)
        self.assertIn("left: 62px; right: 10px; width: auto; transform: none", css)
        self.assertIn(".browser-view.surprise-takeover .browser-list { display: block; }", css)
        self.assertIn("['▶', 'Play this album', 'surprise_play']", app)
        self.assertIn('self.browser_sidebar.set_visible(not data.get("surprise_preview") and not from_discover)', display)
        self.assertIn('("Play Now", "media-playback-start-symbolic", "surprise_play")', display)
        self.assertIn("['↻', 'Surprise me again', 'surprise']", app)
        self.assertIn('self.button("SURPRISE!"', display)
        self.assertNotIn("Surprise Again", app)
        self.assertNotIn("SURPRISE\\nME", display)

    def test_roon_browser_reuses_protected_scroll_layout(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        html = (ROOT / "roon-controller" / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "roon-controller" / "static" / "refinements.css").read_text(encoding="utf-8")
        admin = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.html").read_text(encoding="utf-8")
        self.assertIn('id="browse-tab"', html)
        self.assertIn('id="browser-view"', html)
        self.assertIn(".browser-view { position: fixed", css)
        self.assertIn("inset: 58px 0 96px", css)
        self.assertIn("browser_scroll.set_kinetic_scrolling(True)", display)
        self.assertIn('name="roon_show_browser"', admin)

    def test_roon_browser_uses_section_rail_and_alphabet_scrubber(self):
        display = (ROOT / "native-display" / "pi_bus_native.py").read_text(encoding="utf-8")
        web = (ROOT / "roon-controller" / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "roon-controller" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("def build_browser_keyboard(self):", display)
        self.assertNotIn('id="browser-search"', html)
        self.assertIn('for section in ("albums", "artists", "genres", "playlists")', display)
        self.assertIn('self.browser_scrubber = Gtk.DrawingArea()', display)
        self.assertIn('self.browser_scrubber.set_draw_func(self.draw_browser_scrubber)', display)
        self.assertIn('def browser_scrub_changed(self, scale):', display)
        self.assertIn('self.request_browser("jump", letter=letter)', display)
        self.assertIn('data-browser-section="albums"', html)
        self.assertIn('id="browser-scrubber"', html)
        self.assertIn("browseCommand('jump'", web)
        self.assertIn('browser_cover_card', display)
        self.assertIn("['home', 'menu', 'covers', 'tiles'].includes", web)
        self.assertIn('columns = 4', display)
        self.assertNotIn('self.browser_title', display)
        self.assertIn('sidebar.append(self.browser_back)', display)
        self.assertNotIn('browser_main.append(self.browser_back)', display)
        self.assertIn('cr.set_line_width(5)', display)
        self.assertIn('for _ in range(3): threading.Thread(target=self.thumbnail_worker', display)
        self.assertIn('def maybe_load_more_browser(self):', display)
        self.assertIn('def browser_action_icon(self, title):', display)
        self.assertIn('browser_scroll.set_overlay_scrolling(True)', display)
        self.assertIn('item.get("duration") or ""', display)
        self.assertNotIn('self.button("LOAD MORE"', display)

    def test_admin_system_cards_link_to_animated_in_page_sections(self):
        html = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.html").read_text(encoding="utf-8")
        css = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.css").read_text(encoding="utf-8")
        javascript = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-jump-target="system-maintenance"', html)
        self.assertIn('data-system-anchor="system-device"', html)
        self.assertIn('id="system-maintenance"', html)
        self.assertIn("function openSystemSection(id)", javascript)
        self.assertIn("details[open]>summary::before", css)

    def test_long_now_playing_copy_pauses_and_scrolls_without_polling(self):
        app = (ROOT / "roon-controller" / "static" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "roon-controller" / "static" / "refinements.css").read_text(encoding="utf-8")
        self.assertIn("function setScrollingText(element, text)", app)
        self.assertIn("const startPause = 10000", app)
        self.assertIn("entry.content.animate", app)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertNotIn("setInterval(() => refreshScrollingText", app)

    def test_web_update_control_is_fixed_and_reloads_after_install(self):
        html = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.html").read_text(encoding="utf-8")
        css = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.css").read_text(encoding="utf-8")
        script = (ROOT / "src" / "pi_bus_time_display" / "static" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('class="global-update"', html)
        self.assertIn('class="masthead-actions"', html)
        self.assertIn(".masthead-actions{display:flex", css)
        self.assertNotIn(".global-update{position:fixed", css)
        self.assertIn("setTimeout(()=>location.reload(),1200)", script)
        self.assertIn("const updateButtons=[...document.querySelectorAll", script)
        self.assertIn("function stopUpdateWatch()", script)
        self.assertIn("16*60*1000", script)

    def test_appliance_boot_is_quiet_and_splash_free(self):
        script = (ROOT / "scripts" / "pi-bus-appliance-mode").read_text(encoding="utf-8")
        self.assertIn("disable_splash=1", script)
        self.assertIn("quiet loglevel=3 logo.nologo vt.global_cursor_default=0 systemd.show_status=false", script)
        self.assertIn("^touch2-(5|7|5-7)$", script)


if __name__ == "__main__":
    unittest.main()
