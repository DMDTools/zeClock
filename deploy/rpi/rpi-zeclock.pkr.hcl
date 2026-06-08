# zeClock Raspberry Pi 4 Image — Packer template
# Uses packer-builder-arm to customize a Raspberry Pi OS Lite image in-place

// Note: when building via Docker (mkaczanowski/packer-builder-arm),
// the arm plugin is already available in-container — no required_plugins needed.
// For local builds, install the plugin manually:
//   packer plugins install github.com/mkaczanowski/packer-builder-arm

variable "rpi_os_url" {
  type        = string
  description = "URL to Raspberry Pi OS Lite 64-bit image"
  default     = "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-04-21/2026-04-21-raspios-trixie-arm64-lite.img.xz"
}

variable "rpi_os_checksum" {
  type        = string
  description = "SHA256 checksum of the image (set to empty string to skip verification)"
  default     = "sha256:4cd31df026fd82243805a326dc0cafd7383f7e3d30c9413e7044d507aae281e2"
}

variable "image_size" {
  type        = string
  description = "Final image size (will be expanded)"
  default     = "4.5G"
}

variable "wifi_ssid" {
  type        = string
  description = "Pre-configured WiFi SSID (optional, leave empty for portal-only)"
  default     = ""
}

variable "wifi_password" {
  type        = string
  description = "Pre-configured WiFi password (optional)"
  default     = ""
  sensitive   = true
}

variable "timezone" {
  type        = string
  description = "System timezone"
  default     = "Europe/Paris"
}

variable "hostname" {
  type        = string
  description = "Pi hostname"
  default     = "zeclock"
}

variable "libzedmd_version" {
  type        = string
  description = "libzedmd version tag to build"
  default     = "v0.11.0"
}

source "arm" "rpi_zeclock" {
  file_urls             = [var.rpi_os_url]
  file_checksum         = var.rpi_os_checksum
  file_target_extension = "xz"
  file_unarchive_cmd    = ["xz", "--decompress", "$ARCHIVE_PATH"]

  image_build_method = "reuse"
  image_path         = "zeclock-rpi.img"
  image_size         = var.image_size
  image_type         = "dos"

  image_partitions {
    name         = "boot"
    type         = "c"
    start_sector = 16384
    filesystem   = "vfat"
    size         = "512M"
    mountpoint   = "/boot/firmware"
  }

  image_partitions {
    name         = "root"
    type         = "83"
    start_sector = 1064960
    filesystem   = "ext4"
    size         = "0"
    mountpoint   = "/"
  }

  image_chroot_env = [
    "PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin",
    "DEBIAN_FRONTEND=noninteractive",
  ]

  qemu_binary_source_path      = "/usr/bin/qemu-aarch64-static"
  qemu_binary_destination_path = "/usr/bin/qemu-aarch64-static"
}

build {
  sources = ["source.arm.rpi_zeclock"]

  # Step 1: System + network setup (single apt-get update)
  provisioner "shell" {
    environment_vars = [
      "TIMEZONE=${var.timezone}",
      "HOSTNAME=${var.hostname}",
      "WIFI_SSID=${var.wifi_ssid}",
      "WIFI_PASSWORD=${var.wifi_password}",
    ]
    script = "scripts/01-system-setup.sh"
  }

  # Step 2: Install zeClock (pre-built libzedmd + Python app)
  provisioner "shell" {
    environment_vars = [
      "LIBZEDMD_VERSION=${var.libzedmd_version}",
    ]
    script = "scripts/02-install-zeclock.sh"
  }

  # Copy zeClock source code into the image (clean export, no .git/.venv)
  provisioner "file" {
    source      = "/tmp/zeclock-export/"
    destination = "/tmp/zeclock-src/"
  }

  # Install zeClock from copied source
  provisioner "shell" {
    inline = [
      "mv /tmp/zeclock-src /home/zeclock/app",
      "/home/zeclock/venv/bin/pip install --no-cache-dir /home/zeclock/app",
      "chown -R zeclock:zeclock /home/zeclock",
    ]
  }

  # Create default config that enables the REST API
  provisioner "shell" {
    inline = [
      "mkdir -p /home/zeclock/.zeclock/config",
      "cat > /home/zeclock/.zeclock/config/zeclock.ini << 'EOF'\n[zedmd]\nwifi_addr = \nbrightness = 10\n\n[display]\nfont = STANDARD\n\n[rest_api]\nenabled = true\nhost = 0.0.0.0\nport = 8080\nEOF",
      "chown -R zeclock:zeclock /home/zeclock/.zeclock",
    ]
  }

  # Step 3: Setup read-only overlay filesystem with persistent /data partition
  provisioner "shell" {
    script = "scripts/03-setup-overlay.sh"
  }

  # Copy systemd unit files
  provisioner "file" {
    source      = "files/"
    destination = "/tmp/zeclock-files/"
  }

  # Install unit files and enable services
  provisioner "shell" {
    inline = [
      "cp /tmp/zeclock-files/systemd/*.service /etc/systemd/system/",
      "rm -rf /tmp/zeclock-files",
      "systemctl daemon-reload",
      "systemctl enable zeclock.service",
      "systemctl enable wifi-connect.service",
      "systemctl enable rfkill-unblock-wifi.service",
      "systemctl enable rw-mode.service",
    ]
  }
}
