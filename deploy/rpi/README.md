# zeClock Raspberry Pi 4 Image

Headless Raspberry Pi OS Lite (64-bit) image built with Packer for running zeClock natively.

## Features

- **Headless boot** — no monitor/keyboard needed
- **WiFi auto-connect** — connects to configured WiFi on boot
- **WiFi fallback AP** — if WiFi is unavailable, exposes an access point with a captive portal to configure credentials (uses [wifi-connect](https://github.com/balena-os/wifi-connect))
- **zeClock pre-installed** — Python app + libzedmd + DotClk resources, starts automatically via systemd
- **Power-loss protection** — read-only root filesystem with overlay; survives hard power cuts without SD corruption
- **Persistent /data partition** — F2FS partition for config, WiFi credentials, and application state that persists across reboots

## Prerequisites

- [Packer](https://www.packer.io/) >= 1.9
- [packer-builder-arm](https://github.com/mkaczanowski/packer-builder-arm) plugin
- Linux host (or WSL2) with `qemu-user-static` for ARM64 chroot
- ~4 GB disk space for the build

## Build

```bash
# Install the packer-builder-arm plugin
packer plugins install github.com/mkaczanowski/packer-builder-arm

# Build the image (requires root for loop mounting)
sudo packer build rpi-zeclock.pkr.hcl
```

The output is `zeclock-rpi.img` — flash it to an SD card:

```bash
sudo dd if=zeclock-rpi.img of=/dev/sdX bs=4M status=progress
```

## First boot

1. Insert SD card, power on the Pi
2. If WiFi credentials are pre-configured in `config/wifi.env`, it connects automatically
3. If not (or WiFi is unreachable), the Pi exposes an AP named **zeClock-Setup**
4. Connect to that AP, open a browser → captive portal lets you select a network and enter the password
5. Once connected, zeClock starts automatically

## Configuration

- `config/wifi.env` — optional pre-configured WiFi credentials (baked into image)
- zeClock config is at `/data/zeclock/config/` on the Pi (persistent across reboots)
- WiFi connections are stored on `/data/networkmanager/` (persist across reboots)

## Filesystem Architecture

```
Partition Layout:
  mmcblk0p1  /boot/firmware   FAT32   512M    Boot files (read-only)
  mmcblk0p2  /                ext4    2.5G    Root filesystem (read-only)
  mmcblk0p3  /data            f2fs    ~1G     Persistent data (read-write)
```

The root filesystem is mounted **read-only** at boot. Volatile directories (`/var/log`, `/tmp`, etc.) are backed by tmpfs (RAM). Only `/data` is writable on the SD card, using F2FS which is resilient to power-loss corruption.

### What lives on /data

| Path | Purpose |
|------|---------|
| `/data/zeclock/config/` | zeClock configuration (zeclock.ini) |
| `/data/zeclock/logs/` | Application logs (optional) |
| `/data/zeclock/state/` | Runtime state |
| `/data/networkmanager/` | WiFi connection profiles |
| `/data/ssh/` | SSH host keys (preserved across reflash) |

### Maintenance mode

To make the root filesystem writable temporarily (for updates, debugging):

```bash
# Option 1: Add "nooverlay" to /boot/firmware/cmdline.txt and reboot
# Option 2: Remount manually via SSH
sudo mount -o remount,rw /
```

## Architecture

```
Packer (packer-builder-arm, chroot in .img)
├── Base: Raspberry Pi OS Lite 64-bit (Trixie)
├── scripts/01-system-setup.sh      — locale, timezone, user, NetworkManager
├── scripts/02-install-zeclock.sh   — Python, deps, libzedmd, resources
├── scripts/03-setup-overlay.sh     — read-only root, tmpfs overlays, /data partition
└── files/systemd/                  — systemd units for all services
    ├── zeclock.service             — main clock application
    ├── wifi-connect.service        — WiFi captive portal
    ├── rfkill-unblock-wifi.service — ensure WiFi radio is on
    └── rw-mode.service             — remount rw when "nooverlay" is set
```
