"""Construct all real GTK pages under Xvfb; no privileged/network actions."""
from gi.repository import GLib
from wizard import Wizard

app = Wizard()
app.register(None)
app.refresh = lambda: None
app.activate()
app.progress = {"hostname": "pi-home-lounge", "network": True, "roon": True, "zone": "Lounge", "display": True, "profile": "auto", "rotation": "normal"}
app.snapshot = {"connected": True, "roon": {"zones": [{"name": "Lounge"}]}}
context = GLib.MainContext.default()
for stage in range(6):
    app.stage = stage; app.render()
    for _ in range(30):
        while context.pending(): context.iteration(False)
    assert app.content.get_first_child() is not None
    assert app.footer.get_first_child() is not None
app.stage = 1; app.render()
entry = app.content.get_last_child()
app.select_entry(entry); entry.set_text(""); app.type_key("abc"); app.backspace()
assert entry.get_text() == "ab"
app.toggle_shift()
app.type_key("C")
assert entry.get_text() == "abC"
app.toggle_symbols(); app.type_key("/London")
assert entry.get_text() == "abC/London"
app.window.destroy()
print("Native setup: all six real GTK pages and on-screen keyboard passed under Xvfb (not physical touch acceptance).")
