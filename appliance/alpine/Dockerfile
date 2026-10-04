# Build on ARM64 Linux. No credentials or host configuration enter this image.
FROM alpine:3.24.2
RUN apk add --no-cache alpine-base linux-rpi raspberrypi-bootloader \
    mkinitfs eudev seatd cage wlr-randr mesa-dri-gallium mesa-egl \
    python3 py3-pip py3-setuptools py3-gobject3 py3-cairo gtk4.0 \
    nodejs npm git ca-certificates tzdata font-inter dbus avahi avahi-tools bash
WORKDIR /opt/pi-bus-time-display
COPY pyproject.toml ./
COPY src ./src
COPY native-display ./native-display
COPY scripts/pi-bus-cage-launch ./scripts/pi-bus-cage-launch
COPY roon-controller ./roon-controller
COPY tools/discovery-wire.cjs ./tools/discovery-wire.cjs
COPY config.example.toml .env.example ./
COPY appliance/alpine/ ./appliance/alpine/
RUN sh appliance/alpine/provision.sh
