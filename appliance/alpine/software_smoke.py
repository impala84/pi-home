"""Exercise the official optional installer in a disposable fresh ARM64 image."""
from pathlib import Path
import subprocess
from setup_service import Setup

app = Setup()
app.netdata_install_lock.acquire()
app.install_official_netdata()
status = Path('/var/lib/pi-home/netdata-operation-status').read_text()
assert not status.startswith('Failed:'), status
assert Path('/opt/netdata/bin/netdata').is_file()
assert Path('/etc/init.d/netdata').is_file()
assert Path('/etc/runlevels/default/netdata').exists()
assert Path('/etc/periodic/daily/netdata-updater').exists()
subprocess.run(['/opt/netdata/bin/netdata', '-v'], check=True)
print('Official Netdata installed from the fresh image; service and daily updater present.')
