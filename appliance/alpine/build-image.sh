#!/usr/bin/env bash
# ARM64 Linux factory: writes regular temporary files, never a physical disk.
set -euo pipefail
[[ $(uname -s) == Linux && $(uname -m) == aarch64 ]] || { echo 'Build on ARM64 Linux (or use the GitHub Alpine image workflow).'; exit 1; }
for tool in docker sudo sfdisk mkfs.vfat mkfs.ext4 mcopy truncate dd gzip sha256sum; do command -v "$tool" >/dev/null || { echo "Missing build tool: $tool"; exit 1; }; done
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
out="$repo/dist/alpine"
mkdir -p "$out"
build_dir=$(mktemp -d)
container=
cleanup() {
  if [[ -n $container ]]; then docker rm "$container" >/dev/null; fi
  # Keep failed build files for diagnostics; never recursively delete a target.
  echo "Build working files: $build_dir"
}
trap cleanup EXIT
docker build --platform linux/arm64 -t pi-home-alpine:prototype -f "$repo/appliance/alpine/Dockerfile" "$repo"
container=$(docker create pi-home-alpine:prototype)
mkdir "$build_dir/rootfs" "$build_dir/boot"
docker export "$container" | sudo tar --same-owner -x -C "$build_dir/rootfs"
cp -a "$build_dir/rootfs/boot/." "$build_dir/boot/"
cp "$repo/appliance/alpine/config.txt" "$repo/appliance/alpine/cmdline.txt" "$build_dir/boot/"
truncate -s 256M "$build_dir/boot.fat"
mkfs.vfat -F 32 -n PIBOOT "$build_dir/boot.fat"
mcopy -i "$build_dir/boot.fat" -s "$build_dir/boot/"* ::/
truncate -s 1792M "$build_dir/root.ext4"
sudo mkfs.ext4 -F -L PIROOT -d "$build_dir/rootfs" "$build_dir/root.ext4"
sudo e2fsck -fn "$build_dir/root.ext4"
# Partition 1 starts at 1MiB, partition 2 at 257MiB. No loop device needed.
truncate -s 2050M "$build_dir/pi-home-alpine-prototype.img"
printf 'label: dos\nstart=2048,size=524288,type=c,bootable\nstart=526336,size=3670016,type=83\n' | sfdisk "$build_dir/pi-home-alpine-prototype.img"
dd if="$build_dir/boot.fat" of="$build_dir/pi-home-alpine-prototype.img" bs=1M seek=1 conv=notrunc status=none
dd if="$build_dir/root.ext4" of="$build_dir/pi-home-alpine-prototype.img" bs=1M seek=257 conv=notrunc status=none
gzip -c "$build_dir/pi-home-alpine-prototype.img" > "$out/pi-home-alpine-prototype.img.gz"
(cd "$out" && sha256sum pi-home-alpine-prototype.img.gz > pi-home-alpine-prototype.img.gz.sha256)
cp "$build_dir/rootfs/opt/pi-bus-time-display/appliance/alpine/packages-resolved.txt" "$out/"
git -C "$repo" rev-parse HEAD > "$out/source-commit.txt"
echo "Unverified hardware prototype: $out/pi-home-alpine-prototype.img.gz"
