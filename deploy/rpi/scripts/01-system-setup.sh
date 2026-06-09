#!/bin/bash
# Step 1: Base system + network configuration (combined for single apt-get update)
set -euo pipefail

echo ">>> Configuring base system..."

# Set timezone
ln -sf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
echo "${TIMEZONE}" > /etc/timezone

# Set hostname
echo "${HOSTNAME}" > /etc/hostname
sed -i "s/127.0.1.1.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts

# Create zeclock user with a default password (change on first login)
useradd -m -s /bin/bash -G sudo,dialout zeclock
echo "zeclock:zeclock" | chpasswd
echo "zeclock ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/zeclock

# Disable first-boot user rename wizard (cloud-init / userconf)
rm -f /etc/ssh/sshd_config.d/rename_user.conf 2>/dev/null || true
systemctl disable userconfig 2>/dev/null || true
systemctl mask userconfig 2>/dev/null || true
rm -f /boot/firmware/userconf.txt 2>/dev/null || true
rm -f /boot/firmware/userconf 2>/dev/null || true
# Provide userconf with our user so RPi OS doesn't prompt
# (encrypted password for 'zeclock')
HASH=$(echo "zeclock" | openssl passwd -6 -stdin)
echo "zeclock:${HASH}" > /boot/firmware/userconf.txt
# Disable cloud-init entirely — this is an appliance, not a cloud instance
if [ -d /etc/cloud ]; then
    touch /etc/cloud/cloud-init.disabled
fi
systemctl disable cloud-init 2>/dev/null || true
systemctl mask cloud-init 2>/dev/null || true
systemctl disable cloud-init-local 2>/dev/null || true
systemctl mask cloud-init-local 2>/dev/null || true
systemctl disable cloud-config 2>/dev/null || true
systemctl disable cloud-final 2>/dev/null || true

# Enable SSH
systemctl enable ssh
touch /boot/firmware/ssh

# Pre-generate SSH host keys (required for read-only root — sshd can't generate them at boot)
ssh-keygen -A

# --- Install runtime dependencies from pre-downloaded .deb files ---
# (avoids apt-get update which downloads 27 MB of package lists)
if [ -d /tmp/zeclock-debs ] && [ "$(ls /tmp/zeclock-debs/*.deb 2>/dev/null | wc -l)" -gt 0 ]; then
    dpkg -i /tmp/zeclock-debs/*.deb
    rm -rf /tmp/zeclock-debs
    ldconfig
else
    # Fallback: use apt if .debs not available
    apt-get update
    apt-get install -y --no-install-recommends libserialport0 f2fs-tools
    apt-get clean
    rm -rf /var/lib/apt/lists/*
fi

# --- Network setup ---
echo ">>> Setting up NetworkManager..."

# Disable dhcpcd in favor of NetworkManager
systemctl disable dhcpcd 2>/dev/null || true
systemctl mask dhcpcd 2>/dev/null || true

cat > /etc/NetworkManager/NetworkManager.conf << 'EOF'
[main]
plugins=ifupdown,keyfile

[ifupdown]
managed=true

[device]
wifi.scan-rand-mac-address=no
wifi.backend=wpa_supplicant
EOF

rm -f /etc/wpa_supplicant/wpa_supplicant.conf
# Keep wpa_supplicant available for NetworkManager (don't disable it)

# Ensure WiFi is not rfkill-blocked on first boot
rm -rf /var/lib/systemd/rfkill/*

# Set WiFi as enabled in NetworkManager state (Bookworm uses NM to control rfkill)
mkdir -p /var/lib/NetworkManager
cat > /var/lib/NetworkManager/NetworkManager.state << 'EOF'
[main]
NetworkingEnabled=true
WirelessEnabled=true
WwanEnabled=true
EOF

# Set WiFi regulatory domain (required for Pi WiFi to activate)
if ! grep -q 'cfg80211.ieee80211_regdom' /boot/firmware/cmdline.txt; then
    sed -i 's/$/ cfg80211.ieee80211_regdom=FR/' /boot/firmware/cmdline.txt
fi

# Pre-configure WiFi if credentials provided
if [ -n "${WIFI_SSID:-}" ] && [ -n "${WIFI_PASSWORD:-}" ]; then
    echo ">>> Pre-configuring WiFi: ${WIFI_SSID}"
    nmcli connection add \
        type wifi \
        con-name "preconfigured" \
        ssid "${WIFI_SSID}" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "${WIFI_PASSWORD}" \
        connection.autoconnect yes \
        connection.autoconnect-priority 100
fi

# Enable NetworkManager
systemctl enable NetworkManager

echo ">>> System + network setup complete."
