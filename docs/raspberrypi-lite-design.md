# Raspberry Pi OS Lite target design

Experimental second target; Alpine files and release selection remain unchanged.

## Repository audit and reuse

The application is Python (`src/`), GTK4 (`native-display/`) and a Node Roon
controller (`roon-controller/`). Existing configuration and controller pairing live
under `/etc/pi-home` and `/var/lib/pi-home`; legacy pi-bus paths are aliases.
Debian systemd backend/controller units, the queued privileged system-action path,
Settings UI, NetworkManager actions and display profiles already exist. Reuse them.
The desktop installer/autostart and mutable Git updater are unsuitable for Lite.
Alpine's atomic release engine and safe ext4 expansion logic are reusable via a
small adapter; leave their entrypoints untouched until both targets have hardware
coverage. Alpine setup/wizard embeds OpenRC, APK and musl Bridge handling, so do not
launch it on Debian. Lite uses existing web/touch Settings and Imager credentials
for initial network/admin access. A fully offline touchscreen setup wizard is future
work, not a claim of this prototype.

## Target boundary

`appliance/raspberrypi/`: explicit no-recommends package list, guarded Lite installer,
firstboot service, dedicated seatd/Cage service, staged application updater adapter,
image sealing tooling and test instructions. `appliance/common/`: read-only benchmark
collector usable on both operating systems. Application code stays shared.

## Risks and gates

- Trixie package availability and Pi 5 V3D acceleration require ARM64 hardware checks.
- Dedicated seatd socket/group grants display access without a graphical login or
  PAM desktop session. Cage must own tty1; retain SSH and other recovery consoles.
- Existing original/Touch Display 2 rotation logic must be checked on 7/10-inch
  panels in both orientations; changing panel overlay requires a reboot.
- Grow only a directly mounted ext4 final partition. Failed expansion has no success
  marker, remains retryable and is visible in logs. Preserve administrative access.
- Native official Roon Bridge lives in `/opt/RoonBridge`, with data in `/var/roon`;
  both are outside releases. Vendor self-updates are separate from Pi Home updates.
- Updater must reject releases lacking Lite support before activation, stage all
  dependencies, require running backend/controller/display revision and roll back.
  Do not run apt from application updates. OS dependencies are a tested manual
  maintenance operation. Source releases must retain the Lite target in future.
- Root/system-action queue security follows existing Debian implementation;
  configuring Wi-Fi/display and reboot are deliberate privileged operations.
- Memory/responsiveness targets are hardware evaluation goals, not measured results.
  Netdata absent; no service removal without before/after evidence.

First validate a converted official Lite installation. Full unattended image build,
shrink/compression pipeline and precise tap-to-frame instrumentation remain hardware
and pipeline work; sealing prerequisites are documented separately.
