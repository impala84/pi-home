# Alpine appliance experiment

Isolated branch: `alpine-appliance-prototype`, based on Discover beta.7.
This is an experimental image factory, not a Stable/Beta application update.
Do not install it over the working Pi. Use a separate SD card.

## Verified factory build — 4 October 2026

Installer revision `ce7da54`; [ARM64 installer image and native GTK checks](https://github.com/impala84/pi-home/actions/runs/37185600684)
passed. All six wizard pages and the touch keyboard were exercised under Xvfb
at 800×480; both HTTP services passed in Alpine. Local verification passed
142 Python tests. This supersedes the earlier image for first-boot setup.
New installations use `/opt/pi-home`, `/etc/pi-home` and `/var/lib/pi-home`;
legacy paths are compatibility links for existing runtime helpers. The installer
does not move or overwrite an older installation's saved settings or pairing.

Earlier image-factory baseline:

Source revision `888d8cd`; [ARM64 image build and runtime checks](https://github.com/impala84/pi-home/actions/runs/37183838137)
passed. Artifact `pi-home-alpine-prototype` contains the compressed image,
SHA-256, source revision and resolved package manifest (about 319 MB total).
The persistent root filesystem passed e2fsck. GTK/Graphene/Cairo imports and
both HTTP services passed inside Alpine as the unprivileged application user;
unsupported update requests returned HTTP 501 without creating an action queue.
Baseline CI passed 132 Python and 91 Node tests. These results do not prove Pi
boot, DSI/touch operation, LAN Roon discovery or memory headroom on a 1GB board.
GitHub artifacts expire after 14 days; the factory can rebuild the experiment.

## First milestone

Alpine 3.24.2 ARM64, Raspberry Pi-patched kernel and firmware, persistent
ext4 root filesystem (not a whole-system RAM disk), OpenRC supervised services,
seatd/Cage/Wayland and the existing Python GTK4 native display. Node runs the
existing Roon controller. No desktop, Chromium, SSH or shared root password.
Ethernet DHCP and mDNS are included. Pi Home configuration and Roon pairing
persist on the root filesystem. Bus Times is off; the initial theme is Roon.
The native first-boot wizard now covers device naming, Ethernet/Wi-Fi,
Roon authorisation/zone selection (or explicit setup-later), display profile,
orientation, theme/timezone and a user-chosen web admin password. An on-screen
keyboard avoids requiring SSH or a physical keyboard. Settings are saved per
step and interrupted setup resumes at the first incomplete step. Finish marks
setup complete; subsequent boots go straight into the main native display.

A root-owned Unix socket helper accepts bounded setup actions only from the
local `morningbus` account; it is not an HTTP endpoint. Names, zones, display
profiles and password lengths are validated. Wi-Fi secrets are passed to
NetworkManager without shell interpretation or command-output logging and are
not recorded in the progress file. Privileged setup mutations are locked after
completion (status and an explicit completion reboot remain available).
Existing general-purpose OS/update controls remain disabled in this prototype.

The image is approximately 2 GiB before compression. It does not expand its
partition automatically yet; extra card capacity is unused. Build dependencies
and the exact installed APK versions are recorded alongside the image.
The Alpine base release is fixed, but package repositories can receive updates;
this is not yet a byte-for-byte reproducible or signed image distribution.

## Build

Run the **Alpine appliance prototype** GitHub Actions workflow on this branch.
It uses an ARM64 Linux runner and uploads the compressed `.img.gz`, checksum,
resolved package list and source revision as a 14-day build artifact. It does
not publish to the updater, flash a card, start audio or contact the running Pi.

Alternatively on ARM64 Linux with Docker, sudo, dosfstools, e2fsprogs, fdisk and
mtools installed:

```sh
bash appliance/alpine/build-image.sh
```

The factory formats only regular files under a fresh temporary directory,
never block devices. Root ownership is preserved during rootfs export. Its
temporary files are retained for diagnostics; paths are printed after building.

## First hardware test

Download the successful build artifact; check its SHA-256, then select its
image in Raspberry Pi Imager and flash a **spare** card (flashing erases that
selected card). Start with Pi 5, wired Ethernet and HDMI if necessary to
separate boot bring-up from DSI compatibility. The intended boot path starts
Pi Home automatically; actual boot, DRM/seat ownership and touch are unproven.
Follow the native wizard. It explains Roon Settings → Extensions, lists available
zones and lets you choose a password for web settings (username `admin`).
Use at least ten characters. The password is stored privately, not printed in
logs or embedded in the build artifact. The Finish screen shows the named
device's `.local:8765/admin` address. Use the assigned IP if mDNS is unavailable.
NetworkManager handles Ethernet DHCP and saved Wi-Fi connections. Wi-Fi/DSI,
touch keyboard behaviour and Roon LAN pairing still require physical acceptance.

Display auto-detection is initially enabled. The build must include the Pi 5 device tree
and 10-inch Touch Display 2 overlay, but package presence does not prove hardware
operation. The wizard writes a backed-up, managed display overlay and touch
rotation parameters; Touch Display 2 output rotation uses the existing Cage
launcher on the next boot. Automatic/HDMI and original display profiles support
Normal only in this prototype. The wizard rejects other rotations for those
profiles rather than claiming they work. Display changes require restarting.

## Deliberate limitations

- Roon **controller**, not Roon Bridge audio endpoint. Roon Bridge's Linux
  compatibility/redistribution is a separate gate; this image does not bundle it.
- OS controls (updates, Wi-Fi changes, reboot, profile/rotation, brightness and
  LED actions) reject requests explicitly in prototype mode. Their systemd-based
  privileged worker is not installed. UI settings may still show those controls.
- No recovery console, rootfs expansion, OS
  rollback, update-channel integration or power-loss qualification yet.
- No claim of 1GB viability until measured on real Pi hardware. Record available
  RAM and peaks across Now Playing, Browse, Discover and 24–48-hour operation.
- Container imports and filesystem checks are not an emulated Pi boot, physical
  display validation or a successful one-click public release.

Setup verification includes isolated command-mocked tests for persistence,
validation, interrupted setup, secret handling, rotation and completion locks,
plus real GTK page/keyboard construction under a disposable Xvfb display.
Neither test substitutes for Wi-Fi hardware, Wayland/DSI or actual finger input.

Hardware acceptance: cold boot, DSI/touch, rotation mapping, brightness/sleep/wake,
Roon LAN discovery and pairing persistence, crash recovery, memory peaks,
network interruption and a power-cycle soak. Compare against Pi OS Lite with
the same app and graphical stack before choosing the public base OS.
