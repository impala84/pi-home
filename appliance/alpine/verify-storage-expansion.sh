#!/usr/bin/env bash
# CI-only: emulate flashing the factory image onto a larger card via a loop disk.
set -euo pipefail
image_gz=${1:?usage: verify-storage-expansion.sh image.img.gz}
work=$(mktemp -d)
loop=
cleanup() {
  for path in proc sys dev; do sudo umount "$work/root/$path" 2>/dev/null || true; done
  sudo umount "$work/root" 2>/dev/null || true
  [[ -z $loop ]] || sudo losetup -d "$loop" 2>/dev/null || true
}
trap cleanup EXIT
gzip -dc "$image_gz" > "$work/card.img"
truncate -s 4G "$work/card.img"
loop=$(sudo losetup --find --show --partscan "$work/card.img")
mkdir "$work/root"
sudo mount "${loop}p2" "$work/root"
for path in dev sys proc; do sudo mount --bind "/$path" "$work/root/$path"; done
sudo chroot "$work/root" /usr/bin/python3 /opt/pi-home/appliance/alpine/expand_root.py
test -f "$work/root/var/lib/pi-home/root-storage-expanded"
partition_bytes=$(sudo blockdev --getsize64 "${loop}p2")
filesystem_bytes=$(df -B1 --output=size "$work/root" | tail -1 | tr -d ' ')
test "$partition_bytes" -gt 3500000000
test "$filesystem_bytes" -gt 3400000000
grep -q 'Root storage expansion completed' "$work/root/var/log/pi-home/storage.log"
echo "Fresh-image expansion passed: partition=$partition_bytes filesystem=$filesystem_bytes"
