# Experimental Raspberry Pi OS Lite appliance

This is a second target alongside Alpine. It has not yet been boot-tested on Pi
hardware. No RAM, boot-time or performance claim is made. Start from the current
**Raspberry Pi OS Lite (64-bit), Debian Trixie**, never Desktop.

## First installation

1. In Raspberry Pi Imager choose Pi 4/5 and Raspberry Pi OS Lite (64-bit). Record
   the exact image date/SHA256. Set a unique admin account/password, hostname,
   Wi-Fi country/network if needed, timezone and SSH. Flash a spare card; keep
   the working Alpine card. Boot Lite and connect over Ethernet or configured Wi-Fi.
2. From SSH, run:

   ```sh
   sudo apt-get update
   sudo apt-get install -y --no-install-recommends git
   git clone --branch v1.1.1-beta.4 https://github.com/impala84/pi-home.git
   cd pi-home
   sudo bash appliance/raspberrypi/install.sh touch2-10 90
   sudo reboot
   ```

   `touch2-10 90` is the 10-inch Touch Display 2 in landscape. Use `touch2-10 normal`
   for portrait, `touch2-7 90` / `touch2-7 normal` for 7-inch Touch Display 2,
   or `original normal` / `original 90` for the original 7-inch panel. These
   are panel profiles, not GTK layout dimensions. External HDMI/USB panels need
   their own verified profile; do not assume Touch Display 2 wiring.
   The installer runs from committed source and refuses an existing installation.
   To benchmark without Bridge, prefix the install command with
   `sudo env PI_HOME_SKIP_ROON_BRIDGE=1 bash ...`.
3. Pi Home should boot into Cage/GTK on tty1. Open `http://<hostname>.local:8765`.
   Read the unique web Settings password with
   `sudo cat /etc/pi-home/secrets.env` locally; do not share its contents.
   Use shared touchscreen/web Settings to select orientation, network and Roon.
   Authorize the Pi Home extension in Roon and enable Bridge's ALSA endpoint in
   Roon Settings → Audio. No shared Linux password is created; Imager's account
   is retained. Offline touchscreen account/network setup is not implemented yet.

The default is Beta for evaluation. Stable remains independently controlled;
selecting an older stable release never downgrades this prototype.

## Verify and recover

```sh
systemctl --failed
systemctl status pi-home-firstboot pi-home-seatd pi-bus-native pi-bus-time-display pi-bus-roon-controller roonbridge
journalctl -b -u pi-home-firstboot -u pi-home-seatd -u pi-bus-native --no-pager
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
df -h / /opt/pi-home-releases
sudo cat /var/log/pi-home/storage.log
sudo cat /var/lib/pi-home/storage-status
sudo cat /var/lib/pi-home/raspberrypi-initialized
cat /run/pi-home/display-source-commit
cat /opt/pi-home/.source-commit
aplay -l
sudo journalctl -b -u roonbridge --no-pager
```

Use sudo for the display revision if its private runtime directory is inaccessible.
A 32 GB card should expose almost all remaining space as root after the boot
partition. Expansion detects ext4 and its actual device through sysfs, uses
`growpart` and `resize2fs`, and marks success only after both succeed. If it fails,
SSH and backend remain available, the provisioning marker stays absent and the
next boot retries. Repair the reported cause and retry with
`sudo systemctl restart pi-home-firstboot`. Do not delete partition tables.

Check Cage logs for DRM/seat permission failures. Check `dmesg` for VC4/V3D and
panel/touch errors. Test the renderer inside the Cage session with developer tooling
before claiming accelerated rendering; an SSH GL utility without a display is not
proof. Test touch in every corner after each orientation change and reboot.

Roon's inspected official ARM64 installer installs `/opt/RoonBridge`, data and
identity under `/var/roon`, and a root systemd service. This target uses it natively
and answers its initial confirmation automatically. Its runtime dependency check
must pass; installation fails visibly if the current vendor binary is incompatible.
No container or musl compatibility layer is used. Pi Home updates never touch either
Roon directory. Roon manages its own Bridge binary updates.

An interrupted initial install is not rerun over partial state automatically. Keep
`/var/log/pi-home` and the installer output for diagnosis; for the first experiment,
reflash the spare card and rerun from clean Lite. Repeated boots are idempotent.

## Updates and maintenance

Use System → Software or `sudo pi-bus-update`. The Lite updater shares Alpine's
bounded archive extraction, release selection, storage accounting and atomic link
utilities without changing Alpine's entrypoint. It stages Python/npm dependencies
on disk, activates a new `/opt/pi-home-releases/<commit>-<timestamp>` tree, checks
API/controller plus display revision and stability, and restores the previous
working release on failure. Settings and controller pairing remain outside releases.
No apt operation occurs in this updater. Service-definition or OS package-profile
changes require explicit tested maintenance; old releases lacking Lite support are
rejected before activation. The previous successful release is retained until the
next update needs staging space.

Staging reserve is `max(160 MB, allocated current tree + 96 MB)`, the existing
reviewed Alpine policy. The archive is capped at 30 MB compressed / 100 MB unpacked.
Thus 379 MB free is not rejected by a blanket 400 MB rule, but a genuinely large
installed tree can still require more. Logs: `/var/lib/pi-home/update.log` and
`update-status`. Verify root expansion before reducing safety margins.

OS/package updates are a separate maintenance window: record installed versions,
back up card/configuration, test on a spare card, then deliberately apply selected
updates. Apt background timers are disabled; network/SSH/discovery/time services
remain. No Bluetooth/logging/getty shaving is attempted without measurements.
Netdata is absent. Prefer the System interface and benchmark collector.

Lite's existing zram policy is preserved. If there is no existing swap and measured
spikes justify it, `sudo systemctl enable --now pi-home-zram` enables an optional
256 MiB LZ4 zram device. Inspect `swapon --show` first; the helper refuses an existing
swap policy. Disable with `sudo systemctl disable --now pi-home-zram`. Disk swap is
not added; the old dphys-swapfile service is disabled if present. Confirm the current
base image has no separately configured disk swap before the benchmark.

## A/B protocol

Keep application revision, settings, Roon core/library, artwork cache state, display,
orientation, power supply, CPU policy, network and audio endpoint identical. Run
three cold boots per OS and repeat tests with Bridge both disabled and enabled.
Run collectors as root for PSS visibility (RSS works where proc permissions allow):

```sh
sudo python3 /opt/pi-home/appliance/common/benchmark.py --label idle-no-bridge --duration 600 > idle-no-bridge.jsonl
sudo python3 /opt/pi-home/appliance/common/benchmark.py --label navigation-with-bridge --duration 600 > active.jsonl
sudo python3 /opt/pi-home/appliance/common/benchmark.py --label soak-with-bridge --duration 14400 > soak.jsonl
```

Copy the same collector to Alpine if that branch does not yet contain it. It is
stdlib-only and read-only. Default sample interval is 5 seconds. Record Bridge
state and warm-up duration in filenames/notes; never stop it during playback.
RSS sums can double-count shared pages; use PSS for process attribution and system
`MemTotal - MemAvailable` for overall pressure, including the OS. Compare medians,
95th percentiles and soak drift, swap usage and temperature, against approximately
600 MB excluding Bridge / 750 MB including it. These are evaluation targets.

For each run record:

| Measurement | Repeatable procedure |
|---|---|
| Boot to usable interface | Film power-on through first successful tap, three cold boots; systemd boot time alone omits visible readiness. |
| Idle/active/soak RAM and CPU | Ten-minute idle, same ten-minute navigation sequence, then four-hour soak collector. |
| Navigation and touch | Same 20 Browse/back/album/search taps; film at high frame rate and record median/p95 visible delay; test all corners. |
| Display | Repeat original 7-inch and 10-inch, landscape/portrait; inspect text clipping, swipe, dialogs and touch alignment. |
| Network | Same LAN iperf3 server, 60-second tests separately on Wi-Fi and Ethernet, record RSSI/link speed; install iperf3 only on test cards. |
| Audio | Same ALSA endpoint and track for 30 minutes; verify Roon discovery, dropouts, restart and cold-boot identity. |
| Temperature | Collector during idle, navigation and playback; record ambient temperature and cooling. |
| Roon/API versus GTK | Local collector HTTP times measure cached service responses only. Capture controller/Roon logs and video separately; never label them upstream Roon latency. |

Precise tap → handler → outbound Roon request → response → parse → GTK update →
visible frame spans are not yet instrumented. Until implemented, report UI timings
and Roon request timings separately; film-based visible delay cannot identify which
layer caused it. Do not decide an OS winner from cached HTTP probes.

## Flashable image destination

The initial runtime experiment uses one automated installer after Imager boot.
There is **no published flashable Pi Home Lite image yet**. A future Linux ARM64
image job should pin/verify the official Lite image SHA256, install this committed
target in a disposable guest (retaining Pi firmware/kernel), collect the resolved
package manifest, run runtime checks, seal clean machine state, safely shrink the
unmounted ext4 partition, verify boot on a larger card, compress to
`pi-home-<version>-rpi-arm64.img.xz`, and publish checksum plus provenance.

`seal-image.sh` is a guarded prototype helper (`PI_HOME_DISPOSABLE_IMAGE=1`) for
clean disposable guests only; it refuses paired Roon files and resets application
identity, firstboot/expansion markers, machine-id and SSH keys. It is not a complete
privacy scrub or image builder. A distribution pipeline must also remove test login
credentials, Wi-Fi profiles, secrets, logs and other machine state, provide an
unattended secure initial-account/setup mechanism, and avoid shipping a test admin
account. Never seal or clone an owner's live Pi as a distributable image.
