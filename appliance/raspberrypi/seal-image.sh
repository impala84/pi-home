#!/usr/bin/env bash
# Run only inside a disposable image build, immediately before powering it off.
set -euo pipefail
[[ ${EUID} == 0 && ${PI_HOME_DISPOSABLE_IMAGE:-0} == 1 ]] || { echo 'Requires root and PI_HOME_DISPOSABLE_IMAGE=1 in a disposable image build'; exit 1; }
systemctl stop pi-bus-native pi-bus-time-display pi-bus-roon-controller
systemctl stop roonbridge 2>/dev/null || true
# Refuse to distribute an image that contains real controller/Bridge pairing.
if find /var/lib/pi-home/roon /var/roon -type f -print -quit 2>/dev/null | grep -q .; then
  echo 'Paired Roon data found; rebuild from clean Lite rather than cloning a used appliance'; exit 1
fi
rm -f /var/lib/pi-home/raspberrypi-initialized /var/lib/pi-home/root-storage-expanded /var/lib/pi-home/machine-id
sed -i 's/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=change-me-now/' /etc/pi-home/secrets.env
# Fresh machine/network identities; retain deliberately supplied Imager setup.
rm -f /etc/ssh/ssh_host_*
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
# Ensure SSH host keys regenerate without requiring interactive Linux intervention.
mkdir -p /etc/systemd/system/ssh.service.d
printf '[Service]\nExecStartPre=/usr/bin/ssh-keygen -A\n' > /etc/systemd/system/ssh.service.d/pi-home-image.conf
sync
echo 'Sealed. Power off now; do not boot again before capturing the disposable disk.'
