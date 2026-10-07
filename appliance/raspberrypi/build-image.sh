#!/usr/bin/env bash
# Build a sealed Pi Home image from one pinned official Raspberry Pi OS Lite image.
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
out=${PI_HOME_IMAGE_OUT:-$repo/dist/raspberrypi}
base_url=${PI_HOME_BASE_URL:-https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-10-06/2026-10-06-raspios-trixie-arm64-lite.img.xz}
base_sha256=${PI_HOME_BASE_SHA256:-483db18a48da399b5b7022ffae9a07bc6d99daab30e593aedac09b69ff422843}
source_sha=$(git -c safe.directory="$repo" -C "$repo" rev-parse HEAD)
version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$repo/pyproject.toml")
[[ $(uname -m) == aarch64 && $source_sha =~ ^[0-9a-f]{40}$ && -n $version ]] || { echo 'ARM64 Linux and a committed source revision are required'; exit 1; }

work=$(mktemp -d)
loop=''
root="$work/root"
cleanup() {
  set +e
  mountpoint -q "$root/run" && umount -R "$root/run"
  mountpoint -q "$root/sys" && umount -R "$root/sys"
  mountpoint -q "$root/proc" && umount -R "$root/proc"
  mountpoint -q "$root/dev" && umount -R "$root/dev"
  mountpoint -q "$root/boot/firmware" && umount "$root/boot/firmware"
  mountpoint -q "$root" && umount "$root"
  [[ -z $loop ]] || losetup -d "$loop"
  rm -rf "$work"
}
trap cleanup EXIT

mkdir -p "$out" "$root"
curl --fail --location --retry 4 --output "$work/base.img.xz" "$base_url"
printf '%s  %s\n' "$base_sha256" "$work/base.img.xz" | sha256sum -c -
xz -dc "$work/base.img.xz" > "$work/pi-home.img"
# Add installation headroom. The appliance first-boot service grows partition 2
# again after this image is flashed to the user's larger card.
truncate -s +2560M "$work/pi-home.img"
loop=$(losetup --find --show --partscan "$work/pi-home.img")
[[ -b ${loop}p1 && -b ${loop}p2 ]] || { echo 'Unexpected official image partition layout'; exit 1; }
growpart "$loop" 2
e2fsck -pf "${loop}p2" || [[ $? == 1 ]]
resize2fs "${loop}p2"
mount "${loop}p2" "$root"
mkdir -p "$root/boot/firmware"
mount "${loop}p1" "$root/boot/firmware"

mkdir -p "$root/tmp/pi-home-source"
git -c safe.directory="$repo" -C "$repo" archive HEAD | tar -x -C "$root/tmp/pi-home-source"
printf '#!/bin/sh\nexit 101\n' > "$root/usr/sbin/policy-rc.d"
chmod 755 "$root/usr/sbin/policy-rc.d"
mount --rbind /dev "$root/dev"; mount --make-rslave "$root/dev"
mount -t proc proc "$root/proc"
mount -t sysfs sysfs "$root/sys"
mount -t tmpfs tmpfs "$root/run"
cp --remove-destination /etc/resolv.conf "$root/etc/resolv.conf"
chroot "$root" /usr/bin/env \
  PI_HOME_IMAGE_BUILD=1 \
  PI_HOME_SKIP_ROON_BRIDGE=1 \
  PI_HOME_SOURCE_COMMIT="$source_sha" \
  bash /tmp/pi-home-source/appliance/raspberrypi/install.sh touch2-10 90
chroot "$root" /usr/bin/env PI_HOME_DISPOSABLE_IMAGE=1 PI_HOME_IMAGE_BUILD=1 \
  bash /opt/pi-home/appliance/raspberrypi/seal-image.sh
rm -f "$root/usr/sbin/policy-rc.d"
rm -rf "$root/tmp/pi-home-source"
printf 'nameserver 1.1.1.1\n' > "$root/etc/resolv.conf"
# Refuse to export device identity, credentials, pairing or a half-installed app.
test "$(cat "$root/opt/pi-home/.source-commit")" = "$source_sha"
test -L "$root/etc/systemd/system/multi-user.target.wants/pi-home-firstboot.service"
test -L "$root/etc/systemd/system/multi-user.target.wants/pi-bus-native.service"
test -f "$root/boot/firmware/overlays/vc4-kms-dsi-ili79600-10-1inch.dtbo"
test ! -e "$root/opt/RoonBridge"
test ! -s "$root/etc/machine-id"
test -z "$(find "$root/etc/ssh" -maxdepth 1 -name 'ssh_host_*' -type f -print -quit)"
test -z "$(find "$root/etc/NetworkManager/system-connections" -type f -print -quit 2>/dev/null)"
! awk -F: '$3 >= 1000 && $3 < 65534 { found=1 } END { exit(found ? 0 : 1) }' "$root/etc/passwd"
grep -qx 'ADMIN_PASSWORD=change-me-now' "$root/etc/pi-home/secrets.env"
cp "$root/var/log/pi-home/packages-resolved.txt" "$out/packages-resolved-rpi.txt"
printf '%s\n' "$source_sha" > "$out/source-commit-rpi.txt"
cat > "$out/base-image-rpi.txt" <<EOF
Official base: $base_url
Official SHA-256: $base_sha256
Pi Home source: $source_sha
Pi Home version: $version
Default panel: Touch Display 2 10-inch, landscape
Roon Bridge: not redistributed; install from Pi Home after first boot
EOF
sync
umount -R "$root/run"; umount -R "$root/sys"; umount -R "$root/proc"; umount -R "$root/dev"
umount "$root/boot/firmware"; umount "$root"
e2fsck -fn "${loop}p2"
fsck.vfat -n "${loop}p1"
losetup -d "$loop"; loop=''

image="$out/pi-home-${version}-raspios-lite-arm64.img.xz"
xz -T0 -6 -c "$work/pi-home.img" > "$image"
(cd "$out" && sha256sum "$(basename "$image")" > "$(basename "$image").sha256")
echo "Raspberry Pi OS Lite beta image: $image"
