# Alpine appliance experiment

Current version: **1.1.0-beta.9 Alpine**. Updates stop the display once and restart
backends without OpenRC dependency cascades. Genre, playlist and fallback tiles use
bundled SVGs, not font glyphs. This update is available on the Alpine branch.

Software version labels include “Alpine” (for example, “1.1.0-beta.9 Alpine”)
to distinguish these builds from Raspberry Pi OS. Setup and web password changes
require at least eight characters; setup still requires confirmation.

Isolated branch: `alpine-appliance-prototype`, based on Discover beta.7.
This is an experimental image factory, not a Stable/Beta application update.
Do not install it over the working Pi. Use a separate SD card.

## Physical touch recovery — 4 October 2026

Feature parity follow-up: new images include grim for screenshot capture and
Netdata/OpenRC packages (monitoring remains opt-in, not boot-enabled by the
factory). Netdata status and enable/disable actions now use OpenRC rather than
systemd. Existing images can use System → Services → Install system tools after updating.
This explicit action installs fixed screenshot, process diagnostics, network time
and Netdata packages, without enabling Netdata automatically. Reboot afterwards
applies the transparent touchscreen cursor theme. Application updates do not
silently install OS packages. Updates
now run the root-owned updater from the active application and restart the
private helper as well, avoiding stale service-control code. The first update
from an older image still uses its old standalone updater: restart pi-home-setup
once after that update. Branch selection remains intentionally Alpine-only.

Live bus status showed certificate verification failing because the system
clock was 1970, not because of disabled buses or missing stop configuration.
New images enable chronyd at boot with initial clock stepping. HTTPS certificate
verification remains enabled. Existing images need chrony/chrony-openrc installed
and chronyd enabled once; first correct the clock so HTTPS package/update
downloads can work. Changing timezone alone does not synchronize system time.

The user confirmed direct libinput calibration `0 1 0 -1 0 1` aligns touch
with the 90° clockwise saved setting / Cage transform 270. Live device evidence
showed two separate faults: initial Goodix probe failed with I2C error -5 but
module reload recovered it; its actual name is `10-005d Goodix Capacitive
TouchScreen`, not the unprefixed name used in the old rule. `WL_OUTPUT=DSI-1`
was present in udev but Cage still reported no output mapping.

Current strategy: wildcard the Goodix name prefix, set direct calibration from
the saved orientation, clear WL_OUTPUT, and leave kernel input inversion/swap
off. A bounded two-attempt Goodix reload runs before Cage only when the built-in
GT911 exists and no Goodix input has registered. GTK uses the named invisible
cursor in setup/main, and the empty-event activity exception is guarded.
Live calibration and manual driver recovery are verified by the user; automatic
boot recovery, cursor hiding and updates still need physical acceptance.
The historical image strategies below are superseded; the previous image
`2b48d7b` is not a verified touchscreen image.

## Combined recovery image — 4 October 2026

**Physical test failed:** `764694f` still left touch in portrait coordinates
while the picture was landscape. Its automated checks did not validate touch.
The next revision starts in native orientation with display selection first,
saves the Touch Display 2 kernel overlay's `swapxy`/`invx`/`invy` parameters,
and restarts before continuing to device naming. Cage rotates the picture only;
the Goodix rule explicitly clears `WL_OUTPUT` to prevent double input rotation.
Region/theme remain a later step. This replaces the mapping strategy described
in the historical notes below; physical acceptance is still required.

Revision `2b48d7b`: [image build and native setup checks](https://github.com/impala84/pi-home/actions/runs/37192855390)
passed, including the real GTK first-page choice/reboot request and resume into
device naming, API runtime, SSH policy and updater staging/rollback checks.
Baseline checks passed 156 Python tests and 91 Node tests. For Pi 4B with the
7-inch Touch Display 2, select that exact display and 90° clockwise landscape
on the first screen, then Apply and restart. This is not physical-touch
acceptance; nothing was flashed or remotely installed.

Revision `764694f`: [combined ARM64 image and update checks](https://github.com/impala84/pi-home/actions/runs/37191573089)
passed, including both API services, real GTK setup/icons, SSH policy, real
Python/npm staging, atomic rollback after a simulated failed health check,
and a real HTTP → private Unix socket → root updater privilege-boundary test
using a harmless replacement worker. Baseline checks passed 154 Python and
91 Node tests. OpenRC restarts/health checks in the staging test are simulated;
physical touch mapping, Wi-Fi and subsequent live updates need Pi acceptance.
Includes the explicit Goodix-to-DSI mapping correction, earlier setup/password/
theme improvements and the Alpine application Update button. Nothing was
flashed or installed on the user's device. This supersedes the earlier
rotation-only and setup-only images for the user's next manual test.

## Touch onboarding and SSH revision — 4 October 2026

Physical testing of `c71d326` found that landscape output did not rotate touch.
The earlier assertion that Cage handles both was incomplete: Cage/wlroots only
transforms touch coordinates when the input device is mapped to the output.
The Alpine image did not set that mapping. A new root-owned OpenRC input step
associates only the built-in Goodix touchscreen with the single connected DSI
connector using `WL_OUTPUT`, before Cage opens input devices. Calibration stays
identity and Device Tree input rotation remains off, so rotation has one owner.
Startup logs now record the selected connector/transform and Cage's mapping
messages. This is a source-backed correction, not physical-touch acceptance.
An attached USB mouse can complete onboarding and enable SSH on the already
flashed image, allowing an in-place repair instead of another flash.

Revision `c71d326`: [ARM64 image, GTK pages/icons and SSH policy checks](https://github.com/impala84/pi-home/actions/runs/37189662473)
passed. Baseline checks passed 148 Python and 91 Node tests. Setup now starts
portrait DSI panels in landscape, offers password visibility/confirmation and
an enabled-by-default SSH option, uses a regional timezone chooser, and shows
a small theme-aware Pi Home wordmark. The main splash reads the saved theme
before the first frame. Standard GTK icons and SVG support are included.
Duplicate touch rotation was removed; actual finger input still needs retesting.
No changes were installed on the running Pi, and the earlier image remains
without SSH. This is an experimental image, not an updater release.

## Blank-screen investigation — 4 October 2026

The `ce7da54` installer image failed its first physical Pi 4B / 7-inch Touch
Display 2 test. Direct read-only inspection of that image found `/.dockerenv`
in the root filesystem. OpenRC uses that marker to classify the machine as
Docker; hardware services such as udev exclude containers. The kernel has
VC4, ILI9881 and Goodix support, but suppressing hardware startup prevents the
normal cold-plug/device-module path. This is a confirmed image packaging bug
and a strong explanation for the blank display, not a proven hardware diagnosis.
The image's ext4 filesystem passed a read-only consistency check.

Corrected revision `497b14e`: [image build and exported-root startup checks](https://github.com/impala84/pi-home/actions/runs/37187467742)
passed, alongside the Alpine runtime and native GTK checks. Baseline checks
passed 144 Python and 91 Node tests. The user subsequently confirmed that
this image booted on Pi 4B / 7-inch Touch Display 2; touch, onboarding and
missing icons still needed improvement.

The factory now sanitises the exported root before packaging it: remove Docker
and Podman markers, replace Docker-injected hostname/hosts/DNS configuration,
then check OpenRC reports a non-container system and regenerates dependencies.
Boot output is no longer quiet; OpenRC writes `/var/log/rc.log` and supervised
Pi Home processes write private logs under `/var/log/pi-home/`. Filesystem check
utilities are included. These checks supplement container tests, not physical
Pi boot validation. Do not keep using the earlier `ce7da54` installer image.

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
existing Roon controller. No desktop, Chromium or shared root password.
OpenSSH starts by default, with root login forbidden and only `admin` allowed.
The admin account stays locked until setup saves a confirmed password.
Setup offers Enable SSH, on by default; turning it off stops the service and
removes its boot entry. SSH and web settings share the initial password, but
later password changes are independent. Do not forward SSH to the internet.
SSH host keys are generated on-device, not distributed with the image.
Ethernet DHCP and mDNS are included. Pi Home configuration and Roon pairing
persist on the root filesystem. Bus Times is off; the initial theme is Roon.
The native first-boot wizard now covers device naming, Ethernet/Wi-Fi,
Roon authorisation/zone selection (or explicit setup-later), display profile,
orientation, theme/timezone and a confirmed user-chosen admin password. Fields
offer password visibility, larger touch keys and pressed-state feedback.
Timezone requires a regional choice rather than silently defaulting to UTC.
An on-screen
keyboard avoids requiring SSH or a physical keyboard. Settings are saved per
step and interrupted setup resumes at the first incomplete step. Finish marks
setup complete; subsequent boots go straight into the main native display.

A root-owned Unix socket helper accepts bounded setup actions only from the
local `morningbus` account; it is not an HTTP endpoint. Names, zones, display
profiles and password lengths are validated. Wi-Fi secrets are passed to
NetworkManager without shell interpretation or command-output logging and are
not recorded in the progress file. Privileged setup mutations are locked after
completion (status and an explicit completion reboot remain available).
General-purpose OS controls remain disabled. The Update button now calls a
root-owned local helper, allowed only after setup is complete. It follows the
latest successful Alpine image workflow revision on `alpine-appliance-prototype`,
not arbitrary URLs or Stable/Beta Pi OS releases. Application source and real
Python/npm dependencies are prepared separately under `/opt/pi-home-releases`.
The current path switches atomically after preparation; service health failures
restore the previous application. Configuration, secrets, Wi-Fi and Roon pairing
remain outside deployment directories. Kernel, firmware and APK upgrades are not
performed. Old application deployments are retained for recovery, so repeated
updates need available disk space; automatic retention cleanup is not implemented.

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
operation. The first wizard screen chooses display type and orientation in
native portrait. The wizard writes a backed-up, managed display overlay without
kernel touch rotation and restarts into the naming screen. Cage rotates the
picture only; direct libinput calibration rotates the built-in Goodix input.
Saved orientation wins on later boots and HDMI is left unchanged.
Touch Display 2 output rotation uses the existing Cage
launcher on the next boot. Automatic/HDMI and original display profiles support
Normal only in this prototype. The wizard rejects other rotations for those
profiles rather than claiming they work. Display changes require restarting.

## SSH password recovery

After setup, connect with `ssh admin@DEVICE.local`, using your setup password.
Run `sudo pi-home-reset-password` to enter and confirm a new web password
without printing it or changing your SSH password. Settings and Roon pairing
are retained; restarting the web API invalidates existing web sessions.
The old image has no SSH server, so this cannot retroactively unlock it over
the network. This revision still requires a new image or local shell access.

## Deliberate limitations

- Roon **controller**, not Roon Bridge audio endpoint. Roon Bridge's Linux
  compatibility/redistribution is a separate gate; this image does not bundle it.
- OS controls (Wi-Fi changes, reboot, profile/rotation, brightness and
  LED actions) reject requests explicitly in prototype mode. Their systemd-based
  privileged worker is not installed. UI settings may still show those controls.
- No recovery console, rootfs expansion, OS rollback, Stable/Beta OS-channel
  integration or power-loss qualification yet. Application rollback is present;
  the new image starts with atomic deployment links, but power-loss safety is
  not qualified and runtime checks do not prove physical touch correctness.
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
