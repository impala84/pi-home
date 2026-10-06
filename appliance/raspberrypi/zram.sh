#!/bin/sh
# Opt-in only after measuring; preserve any stock Lite swap/zram policy.
set -eu
if [ "$(wc -l < /proc/swaps)" -gt 1 ]; then
  echo 'Existing swap policy detected; refusing a second zram policy'; exit 1
fi
modprobe zram num_devices=1
echo lz4 > /sys/block/zram0/comp_algorithm
echo 268435456 > /sys/block/zram0/disksize
mkswap /dev/zram0
swapon -p 100 /dev/zram0
