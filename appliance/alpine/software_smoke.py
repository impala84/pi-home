"""Exercise the official optional installer in a disposable fresh ARM64 image."""
from pathlib import Path
import subprocess
from setup_service import Setup

def test_command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise ValueError(str(arguments) + ': ' + result.stdout + result.stderr)
    return result.stdout.strip()

# OpenRC is not PID 1 in this disposable runtime test.
Path('/run/openrc').mkdir(exist_ok=True)
Path('/run/openrc/softlevel').write_text('default\n')
app = Setup(run=test_command)
app.netdata_install_lock.acquire()
app.install_official_netdata()
status = Path('/var/lib/pi-home/netdata-operation-status').read_text()
assert not status.startswith('Failed:'), status
assert Path('/opt/netdata/bin/netdata').is_file()
assert Path('/etc/init.d/netdata').is_file()
assert Path('/etc/runlevels/default/netdata').exists()
assert Path('/etc/periodic/daily/netdata-updater').exists()
config = Path('/opt/netdata/etc/netdata/netdata.conf').read_text()
assert 'enabled = no' in config and 'update every = 3' in config, config
assert Path('/var/lib/pi-home/netdata-lightweight').read_text().strip() == 'yes'
subprocess.run(['/opt/netdata/bin/netdata', '-v'], check=True)
print('Official Netdata installed from the fresh image; service and daily updater present.')
