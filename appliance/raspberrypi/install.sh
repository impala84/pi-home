#!/usr/bin/env bash
# Convert an official, already booted Raspberry Pi OS Lite ARM64 installation.
set -euo pipefail
[[ ${EUID} == 0 ]] || { echo 'Run with sudo'; exit 1; }
[[ $(uname -m) == aarch64 && $(dpkg --print-architecture) == arm64 ]] || { echo 'ARM64 required'; exit 1; }
[[ -f /etc/rpi-issue ]] || { echo 'Official Raspberry Pi OS required'; exit 1; }
. /etc/os-release
[[ ${VERSION_CODENAME:-} == trixie ]] || { echo 'This package profile targets current Trixie Lite'; exit 1; }
for package in raspberrypi-ui-mods lightdm gdm3 chromium; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -qx 'install ok installed'; then
    echo "Use a clean Lite image; desktop component present: $package"; exit 1
  fi
done
[[ ! -e /opt/RoonBridge ]] || { echo 'Existing Bridge detected; use a clean Lite installation'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
profile=${1:-original}
rotation=${2:-normal}
image_build=${PI_HOME_IMAGE_BUILD:-0}
[[ $profile =~ ^(original|touch2-5|touch2-7|touch2-10)$ && $rotation =~ ^(normal|90|180|270)$ ]] || { echo 'Usage: install.sh [original|touch2-5|touch2-7|touch2-10] [normal|90|180|270]'; exit 2; }
[[ ! -e /opt/pi-home && ! -L /opt/pi-home && ! -e /opt/pi-bus-time-display ]] || { echo 'Existing application found; use its updater, not this clean installer'; exit 1; }
install -d -m 0755 /var/log/pi-home
# Capture baseline before installing/removing services.
dpkg-query -W > /var/log/pi-home/packages-before.txt
if [[ $image_build == 1 ]]; then
  printf 'Captured during offline image construction; no service manager was running.\n' > /var/log/pi-home/services-before.txt
else
  systemctl list-units --type=service --all --no-pager > /var/log/pi-home/services-before.txt
fi
free -b > /var/log/pi-home/memory-before.txt
apt-get update
mapfile -t packages < <(sed '/^#/d; /^[[:space:]]*$/d' "$source_dir/appliance/raspberrypi/packages/runtime.txt")
apt-get install -y --no-install-recommends "${packages[@]}"
id morningbus >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/pi-home --shell /usr/sbin/nologin morningbus
usermod -a -G video,render,input,audio morningbus
install -d -m 0755 /opt/pi-home-releases
initial=/opt/pi-home-releases/initial-image
[[ ! -e $initial ]] || { echo 'Incomplete previous install: preserve logs and repair initial-image before retrying'; exit 1; }
mkdir "$initial"
if git -c safe.directory="$source_dir" -C "$source_dir" rev-parse HEAD >/dev/null 2>&1; then
  git -c safe.directory="$source_dir" -C "$source_dir" archive HEAD | tar -x -C "$initial"
  git -c safe.directory="$source_dir" -C "$source_dir" rev-parse HEAD > "$initial/.source-commit"
else
  [[ ${PI_HOME_SOURCE_COMMIT:-} =~ ^[0-9a-f]{40}$ ]] || { echo 'Image build requires PI_HOME_SOURCE_COMMIT'; exit 1; }
  tar -C "$source_dir" --exclude=.git --exclude=.venv -cf - . | tar -x -C "$initial"
  printf '%s\n' "$PI_HOME_SOURCE_COMMIT" > "$initial/.source-commit"
fi
python3 -m venv --system-site-packages "$initial/.venv"
"$initial/.venv/bin/pip" install --no-build-isolation --no-deps "$initial"
npm --prefix "$initial/roon-controller" ci --omit=dev --no-audit --no-fund
ln -s "$initial" /opt/pi-home
install -d -o morningbus -g morningbus -m 0750 /etc/pi-home /var/lib/pi-home /var/lib/pi-home/roon
for parent in /opt /etc /var/lib; do
  [[ ! -e $parent/pi-bus-time-display ]] || { echo "Conflicting legacy path: $parent"; exit 1; }
  ln -s "$parent/pi-home" "$parent/pi-bus-time-display"
done
[[ -f /etc/pi-home/config.toml ]] || install -o morningbus -g morningbus -m 0640 "$initial/config.example.toml" /etc/pi-home/config.toml
[[ -f /etc/pi-home/secrets.env ]] || install -o morningbus -g morningbus -m 0600 "$initial/.env.example" /etc/pi-home/secrets.env
sed -i 's/^release_channel = "stable"/release_channel = "beta"/; s/^display_theme = "fresh-mint"/display_theme = "roon"/' /etc/pi-home/config.toml
install -o morningbus -g morningbus -m 0640 /dev/null /etc/pi-home/roon.env
printf '%s\n' morningbus > /etc/pi-home/display-user
printf '%s\n' "$profile" > /etc/pi-home/display-profile
printf '%s\n' "$rotation" > /etc/pi-home/display-transform
chmod 755 "$initial/native-display/pi_bus_native.py" "$initial/scripts/pi-bus-cage-launch" "$initial/appliance/raspberrypi/display-session"
install -m 0644 "$initial"/systemd/*.service "$initial"/systemd/*.path /etc/systemd/system/
install -m 0644 "$initial"/appliance/raspberrypi/services/* /etc/systemd/system/
for helper in pi-bus-system-action pi-bus-appliance-mode; do
  ln -s "/opt/pi-home/scripts/$helper" "/usr/local/sbin/$helper"
done
# Application updater entrypoint remains stable and resolves through the active link.
cat > /usr/local/sbin/pi-bus-update <<'UPDATE'
#!/bin/sh
exec /usr/bin/python3 /opt/pi-home/appliance/raspberrypi/updater.py
UPDATE
chmod 755 /usr/local/sbin/pi-bus-update
# Existing shared settings helper uses profile-driven overlays and touch mapping.
PI_HOME_NO_RESTART=1 /usr/local/sbin/pi-bus-appliance-mode display "$profile" "$rotation"
# Prevent rotate from replacing the Lite-specific seatd session unit.
mkdir -p /etc/systemd/system/pi-bus-native.service.d
cat > /etc/systemd/system/pi-bus-native.service.d/lite.conf <<'DISPLAY'
[Unit]
Requires=pi-home-seatd.service
After=pi-home-seatd.service pi-home-firstboot.service
[Service]
PAMName=
StandardInput=null
RuntimeDirectory=pi-home
RuntimeDirectoryMode=0700
Environment=XDG_RUNTIME_DIR=/run/pi-home
Environment=LIBSEAT_BACKEND=seatd
Environment=SEATD_SOCK=/run/pi-home-seatd.sock
SupplementaryGroups=video render input audio
ExecStart=
ExecStart=/opt/pi-home/appliance/raspberrypi/display-session
DISPLAY
# Require firstboot before backends even if they are started independently.
for service in pi-bus-time-display pi-bus-roon-controller; do
  mkdir -p "/etc/systemd/system/$service.service.d"
  printf '[Unit]\nWants=pi-home-firstboot.service\nAfter=pi-home-firstboot.service\n' > "/etc/systemd/system/$service.service.d/lite.conf"
done
# Only explicit package background updates are disabled. Keep discovery/network/SSH.
if [[ $image_build == 1 ]]; then
  systemctl disable apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
  if systemctl cat dphys-swapfile.service >/dev/null 2>&1; then systemctl disable dphys-swapfile.service; fi
else
  systemctl disable --now apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
  if systemctl cat dphys-swapfile.service >/dev/null 2>&1; then systemctl disable --now dphys-swapfile.service; fi
fi
# Current Lite may ship a zram policy; preserve it. Additional zram is opt-in.
systemctl mask getty@tty1.service
systemctl set-default multi-user.target
[[ $image_build == 1 ]] || systemctl daemon-reload
systemctl enable NetworkManager avahi-daemon ssh pi-home-seatd pi-home-firstboot pi-bus-native pi-bus-time-display pi-bus-roon-controller pi-bus-system-action.path pi-home-leds
# A sealed image must generate its device identity, web secret and expanded root
# only after it has been flashed. It must not redistribute Roon's binaries.
if [[ $image_build != 1 ]]; then
  python3 "$initial/appliance/raspberrypi/firstboot.py"
fi
if [[ $image_build != 1 && ${PI_HOME_SKIP_ROON_BRIDGE:-0} != 1 ]]; then
  printf 'y\n' | bash "$initial/scripts/install-roon-bridge.sh"
  mkdir -p /etc/systemd/system/roonbridge.service.d
  printf '[Service]\nEnvironment=ROON_DATAROOT=/var/roon\nRestart=on-failure\nRestartSec=5\n' > /etc/systemd/system/roonbridge.service.d/pi-home.conf
  systemctl daemon-reload
  systemctl enable --now roonbridge.service
  systemctl restart roonbridge.service
fi
dpkg-query -W > /var/log/pi-home/packages-resolved.txt
systemctl list-unit-files --no-pager > /var/log/pi-home/services-after.txt
echo 'Installed experimental Lite appliance. Reboot; use existing Imager SSH credentials.'
echo 'Web Settings password is in /etc/pi-home/secrets.env (sudo required).'
