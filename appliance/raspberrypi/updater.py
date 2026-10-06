#!/usr/bin/env python3
"""Lite application-only staging; reuse tested Alpine archive/storage utilities."""
import fcntl
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
import urllib.request
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('stage_utilities', ROOT / 'appliance/alpine/updater.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
APP = shared.APP
STATE = shared.STATE
SERVICES = ('pi-bus-time-display.service', 'pi-bus-roon-controller.service')


def select_revision():
    config = tomllib.loads(shared.CONFIG.read_text())
    version = tomllib.loads((APP / 'pyproject.toml').read_text())['project']['version']
    release = shared.select_release(shared.published_releases(), config.get('release_channel', 'stable'), version, 'rpi')
    if not release['update_available']:
        if release['status'] == 'unavailable':
            raise RuntimeError(release['message'])
        return None
    obj = shared.fetch_json(shared.REPO + '/git/ref/tags/' + release['tag']).get('object', {})
    if obj.get('type') == 'tag' and re.fullmatch('[0-9a-f]{40}', obj.get('sha', '')):
        obj = shared.fetch_json(shared.REPO + '/git/tags/' + obj['sha']).get('object', {})
    if obj.get('type') != 'commit' or not re.fullmatch('[0-9a-f]{40}', obj.get('sha', '')):
        raise RuntimeError('Invalid published release revision')
    return obj['sha']


def compatible(source):
    if not (source / 'appliance/raspberrypi/updater.py').is_file():
        raise RuntimeError('This release predates Lite support; choose a newer channel release')
    for directory in ('systemd', 'appliance/raspberrypi/services'):
        before = {p.name: p.read_bytes() for p in (APP / directory).glob('*') if p.is_file()}
        after = {p.name: p.read_bytes() for p in (source / directory).glob('*') if p.is_file()}
        if before != after:
            raise RuntimeError('Service definitions changed; apply tested appliance maintenance first')
    if (source / 'appliance/raspberrypi/packages/runtime.txt').read_bytes() != (APP / 'appliance/raspberrypi/packages/runtime.txt').read_bytes():
        raise RuntimeError('This release changes OS dependencies; apply tested OS maintenance first')


def restart():
    shared.run(['systemctl', 'stop', 'pi-bus-native.service'], timeout=45)
    shared.run(['systemctl', 'restart', *SERVICES], timeout=45)
    shared.DISPLAY_REVISION.unlink(missing_ok=True)
    shared.run(['systemctl', 'start', 'pi-bus-native.service'], timeout=45)


def healthy(sha):
    restarts = subprocess.check_output(['systemctl', 'show', 'pi-bus-native.service', '-p', 'NRestarts', '--value'], text=True).strip()
    for _ in range(30):
        try:
            for url in ('http://127.0.0.1:8765/api/status', 'http://127.0.0.1:8766/api/state'):
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status != 200:
                        raise OSError('Backend not ready')
            shared.run(['systemctl', 'is-active', '--quiet', 'pi-bus-native.service'], timeout=10)
            if shared.DISPLAY_REVISION.read_text().strip() != sha:
                raise OSError('Old display revision')
            time.sleep(5)
            after = subprocess.check_output(['systemctl', 'show', 'pi-bus-native.service', '-p', 'NRestarts', '--value'], text=True).strip()
            return restarts == after and subprocess.run(['systemctl', 'is-active', '--quiet', 'pi-bus-native.service']).returncode == 0
        except (OSError, RuntimeError, subprocess.SubprocessError):
            time.sleep(1)
    return False


def prepare(target, sha):
    # Archive and extracted source share the destination filesystem, not RAM tmpfs.
    with tempfile.TemporaryDirectory(prefix='.source-', dir=target.parent) as folder:
        temporary = Path(folder)
        archive = temporary / 'source.tar.gz'
        with urllib.request.urlopen('https://codeload.github.com/impala84/pi-home/tar.gz/' + sha, timeout=60) as response, archive.open('wb') as output:
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 30_000_000:
                    raise RuntimeError('Source download too large')
                output.write(chunk)
        source = shared.extract_source(archive, temporary / 'unpacked')
        compatible(source)
        source.rename(target)
    (target / '.source-commit').write_text(sha + '\n')
    shared.run(['python3', '-m', 'venv', '--system-site-packages', str(target / '.venv')])
    shared.run([str(target / '.venv/bin/pip'), 'install', '--no-build-isolation', '--no-deps', str(target)])
    shared.run(['npm', '--prefix', str(target / 'roon-controller'), 'ci', '--omit=dev', '--no-audit', '--no-fund'])
    shared.run([str(target / '.venv/bin/python'), '-c', "import gi; gi.require_version('Gtk', '4.0'); gi.require_foreign('cairo'); from pi_bus_time_display import __version__"])
    for file in ('native-display/pi_bus_native.py', 'scripts/pi-bus-cage-launch', 'appliance/raspberrypi/display-session'):
        (target / file).chmod(0o755)


def update():
    os.chdir('/')
    shared.wait_for_clock()
    shared.status('Update · Checking published application releases…')
    sha = select_revision()
    if sha is None:
        shared.status('Update unchanged. No newer published release for this channel.'); return
    current = APP.resolve()
    releases = current.parent
    if releases != Path('/opt/pi-home-releases') or not APP.is_symlink():
        raise RuntimeError('Unexpected release layout; current application unchanged')
    # Keep the previous rollback release until a new update actually needs its space.
    shared.prune_releases(releases, {current})
    needed = shared.required_stage_space(current)
    available = shutil.disk_usage(releases).free
    if available < needed:
        raise RuntimeError(f'Not enough staging space: {needed // 1_000_000} MB required, {available // 1_000_000} MB available')
    target = releases / (sha + '-' + str(time.time_ns()))
    try:
        shared.status('Update · Preparing application without changing the running release…')
        prepare(target, sha)
    except Exception:
        if target.exists(): shutil.rmtree(target)
        raise
    try:
        shared.activate(target)
        restart()
        if not healthy(sha): raise RuntimeError('New services or GTK display failed readiness checks')
    except Exception as failure:
        shared.activate(current)
        restart()
        previous_sha = (current / '.source-commit').read_text().strip()
        if not healthy(previous_sha):
            raise RuntimeError('Previous application restored; services require attention') from failure
        shutil.rmtree(target)
        raise RuntimeError('Update failed; previous working application restored') from failure
    shared.status('Update installed. Settings, pairing and native Bridge preserved.')


def main():
    if os.geteuid() != 0: raise SystemExit('Run with sudo')
    with open('/run/pi-home-update.lock', 'a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        try: update()
        except Exception as error:
            shared.status('Failed: ' + (str(error) if isinstance(error, RuntimeError) else 'See private update log and journal'))
            raise SystemExit(1)

if __name__ == '__main__': main()
