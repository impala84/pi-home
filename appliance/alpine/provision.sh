#!/bin/sh
# Runs only inside the disposable image build, never on the existing Pi.
set -eu
test "$(uname -m)" = aarch64
test -f /etc/alpine-release
adduser -D -h /var/lib/pi-bus-time-display morningbus
addgroup morningbus video
addgroup morningbus input
mkdir -p /etc/pi-bus-time-display /var/lib/pi-bus-time-display/roon
cp config.example.toml /etc/pi-bus-time-display/config.toml
sed -i 's/display_theme = "fresh-mint"/display_theme = "roon"/' /etc/pi-bus-time-display/config.toml
cp .env.example /etc/pi-bus-time-display/secrets.env
printf '%s\n' 'ALPINE PROTOTYPE: OS controls and in-app updates are not available.' > /var/lib/pi-bus-time-display/update-status
chmod 600 /etc/pi-bus-time-display/secrets.env
chown -R morningbus:morningbus /etc/pi-bus-time-display /var/lib/pi-bus-time-display
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --no-build-isolation --no-deps .
npm --prefix roon-controller ci --omit=dev --no-audit --no-fund
chmod 755 native-display/pi_bus_native.py scripts/pi-bus-cage-launch
chmod 755 appliance/alpine/display-session
cp appliance/alpine/init.d/* /etc/init.d/
chmod 755 /etc/init.d/pi-home-*
cp appliance/alpine/display-launch /usr/local/bin/pi-home-display-launch
chmod 755 /usr/local/bin/pi-home-display-launch
printf '%s\n' 'command_args="-g video"' > /etc/conf.d/seatd
printf '%s\n' 'pi-home-alpine' > /etc/hostname
printf '%s\n' 'auto lo' 'iface lo inet loopback' > /etc/network/interfaces
mkdir -p /etc/NetworkManager/conf.d
printf '%s\n' '[main]' 'plugins=keyfile' '[device]' 'wifi.backend=wpa_supplicant' > /etc/NetworkManager/conf.d/pi-home.conf
printf '%s\n' 'LABEL=PIROOT / ext4 defaults,noatime 0 1' 'LABEL=PIBOOT /boot vfat defaults 0 2' > /etc/fstab
for service in devfs dmesg mdev; do rc-update add "$service" sysinit; done
rc-update del mdev sysinit
rc-update add udev sysinit
rc-update add udev-trigger sysinit
for service in hwclock modules sysctl bootmisc hostname localmount hwdrivers; do rc-update add "$service" boot; done
for service in killprocs savecache mount-ro; do rc-update add "$service" shutdown; done
for service in networking dbus NetworkManager avahi-daemon seatd pi-home-firstboot pi-home-api pi-home-roon pi-home-setup pi-home-display; do rc-update add "$service" default; done
# No SSH, shared password or interactive root console in a distributed image.
passwd -l root
sed -i '/^[^#].*getty/s/^/#/' /etc/inittab
printf '%s\n' 'features="base mmc ext4"' > /etc/mkinitfs/mkinitfs.conf
kernel_version=$(find /lib/modules -mindepth 1 -maxdepth 1 -type d | head -n 1)
mkinitfs "${kernel_version##*/}"
test -s /boot/vmlinuz-rpi
test -s /boot/initramfs-rpi
test -s /boot/bcm2712-rpi-5-b.dtb
test -s /boot/overlays/vc4-kms-dsi-ili79600-10-1inch.dtbo
# Record the exact resolved package versions; repositories may receive fixes.
apk info -vv > /opt/pi-bus-time-display/appliance/alpine/packages-resolved.txt
