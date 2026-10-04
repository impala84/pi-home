"""Real staged dependency installation and rollback in a disposable container.

Source comes from the workflow's git archive. Network and OpenRC actions are
replaced; physical touchscreen acceptance is not implied by this check.
"""
from pathlib import Path
from unittest.mock import patch
import updater

archive = Path("/tmp/pi-home-update-source.tar.gz")
events = []
real_urlopen = updater.urllib.request.urlopen

def source_url(url, **kwargs):
    if isinstance(url, str) and url.startswith("https://codeload.github.com/"): return archive.open("rb")
    return real_urlopen(url, **kwargs)

with patch.object(updater, "verified_revision", return_value="a" * 40), patch.object(updater.urllib.request, "urlopen", side_effect=source_url), patch.object(updater, "restart", side_effect=lambda: events.append("restart")), patch.object(updater, "healthy", return_value=True):
    updater.update()
assert updater.APP.is_symlink()
assert (updater.APP / ".venv/bin/pi-home").exists()
assert (updater.APP / "roon-controller/node_modules").exists()
previous = updater.APP.resolve()
with patch.object(updater, "verified_revision", return_value="b" * 40), patch.object(updater.urllib.request, "urlopen", side_effect=source_url), patch.object(updater, "restart", side_effect=lambda: events.append("restart")), patch.object(updater, "healthy", side_effect=[False, True]):
    try: updater.update()
    except RuntimeError as error: assert "restored" in str(error)
    else: raise AssertionError("Failed health check did not roll back")
assert updater.APP.resolve() == previous
assert events == ["restart", "restart", "restart"]
print("Real Alpine Python/npm staging and atomic rollback passed; OpenRC/health checks simulated, not a Pi boot.")
