#!/bin/bash
# Step 3: Setup read-only overlay filesystem with persistent /data partition
#
# Uses initramfs-based overlayfs (chesty/overlayroot method) since the native
# raspi-config overlayfs relies on the "overlayroot" package which is NOT
# available in Debian Trixie repos (confirmed bug, raspi-config issue #266).
#
# Architecture after boot:
#   overlay on /          — tmpfs upper + ext4 lower (read-only SD card)
#   /overlay/lower        — the real ext4 rootfs (read-only)
#   /boot/firmware        — FAT32, read-only
#   /data                 — f2fs partition (read-write, persistent)
#
# To disable overlay for maintenance, add "skipoverlay" to cmdline.txt
set -euo pipefail

echo ">>> Setting up read-only overlay filesystem..."

# --- f2fs-tools is installed in 01-system-setup.sh ---

# --- Create /data mountpoint ---
mkdir -p /data

# ==========================================================================
# 1. Install initramfs overlay scripts (chesty/overlayroot method)
#    https://github.com/chesty/overlayroot
# ==========================================================================

# Hook: ensures overlay module and busybox are included in initramfs
cat > /etc/initramfs-tools/hooks/overlay << 'HOOK'
#!/bin/sh

PREREQ=""
prereqs()
{
    echo "$PREREQ"
}

case $1 in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /usr/share/initramfs-tools/hook-functions

copy_exec /sbin/fsck
copy_exec /sbin/fsck.ext4
manual_add_modules overlay
HOOK
chmod +x /etc/initramfs-tools/hooks/overlay

# Init-bottom script: mounts overlayfs over root
cat > /etc/initramfs-tools/scripts/init-bottom/overlay << 'INITBOTTOM'
#!/bin/sh

PREREQ=""
prereqs()
{
   echo "$PREREQ"
}

case $1 in
prereqs)
   prereqs
   exit 0
   ;;
esac

. /scripts/functions

# Allow disabling overlay via kernel cmdline
if grep -q -E '(^|\s)skipoverlay(\s|$)' /proc/cmdline; then
    log_begin_msg "Skipping overlay, found 'skipoverlay' in cmdline"
    log_end_msg
    exit 0
fi

log_begin_msg "Starting overlay"
log_end_msg

mkdir -p /overlay

# Use tmpfs for the overlay (writes go to RAM, lost on reboot)
mount -t tmpfs tmpfs /overlay

mkdir -p /overlay/upper
mkdir -p /overlay/work
mkdir -p /overlay/lower

# Move the real root to /overlay/lower (read-only)
mount -n -o move ${rootmnt} /overlay/lower
mount -t overlay overlay -olowerdir=/overlay/lower,upperdir=/overlay/upper,workdir=/overlay/work ${rootmnt}

# Make overlay internals accessible from booted system
mkdir -p ${rootmnt}/overlay
mount -n -o rbind /overlay ${rootmnt}/overlay

# Fix fstab so systemd doesn't try to remount root from the real device
cp ${rootmnt}/etc/fstab ${rootmnt}/etc/fstab.orig
awk '$2 != "/" {print $0}' ${rootmnt}/etc/fstab.orig > ${rootmnt}/etc/fstab
awk '$2 == "'${rootmnt}'" { $2 = "/" ; print $0}' /etc/mtab >> ${rootmnt}/etc/fstab

exit 0
INITBOTTOM
chmod +x /etc/initramfs-tools/scripts/init-bottom/overlay

# Add overlay module to initramfs modules list
if ! grep -q "^overlay" /etc/initramfs-tools/modules; then
    echo "overlay" >> /etc/initramfs-tools/modules
fi

# Regenerate initramfs
update-initramfs -u -k all

# ==========================================================================
# 2. Disable services incompatible with overlay/read-only root
# ==========================================================================

# Disable partition resize
systemctl disable rpi-resize.service 2>/dev/null || true
systemctl mask rpi-resize.service 2>/dev/null || true

# Disable swap services
systemctl disable rpi-swap-file.service 2>/dev/null || true
systemctl mask rpi-swap-file.service 2>/dev/null || true
systemctl disable dphys-swapfile 2>/dev/null || true
systemctl mask dphys-swapfile 2>/dev/null || true
rm -f /var/swap

# Disable apt timers (can't update on RO root)
systemctl mask apt-daily.timer 2>/dev/null || true
systemctl mask apt-daily-upgrade.timer 2>/dev/null || true

# Remove firstboot init from cmdline.txt if present
sed -i 's| init=/usr/lib/raspberrypi-sys-mods/firstboot||' /boot/firmware/cmdline.txt 2>/dev/null || true

# Remove broken overlayroot=tmpfs if present (Ubuntu mechanism, not ours)
sed -i 's/overlayroot=tmpfs //' /boot/firmware/cmdline.txt 2>/dev/null || true

# Remove fsck.repair=yes (not needed with overlay) and resize flag
sed -i 's| fsck.repair=yes||' /boot/firmware/cmdline.txt 2>/dev/null || true
sed -i 's| resize||' /boot/firmware/cmdline.txt 2>/dev/null || true

# ==========================================================================
# 3. First-boot service: create and format /data partition
# ==========================================================================

cat > /usr/local/sbin/setup-data-partition.sh << 'SETUPSCRIPT'
#!/bin/bash
# Create /data partition (p3) if it doesn't exist, format as f2fs, mount it.
# On subsequent boots, just mount it if already formatted.
set -e

DEVICE="/dev/mmcblk0p3"
DISK="/dev/mmcblk0"

# Already mounted? Done.
if mountpoint -q /data 2>/dev/null; then
    exit 0
fi

# If partition exists and is f2fs, just mount it
if [ -b "${DEVICE}" ]; then
    CURRENT_FS=$(blkid -s TYPE -o value "${DEVICE}" 2>/dev/null || echo "")
    if [ "${CURRENT_FS}" = "f2fs" ]; then
        mount -t f2fs -o noatime "${DEVICE}" /data
        exit 0
    fi
fi

# Partition doesn't exist — create it using remaining SD card space
if [ ! -b "${DEVICE}" ]; then
    echo "setup-data: creating partition 3 on ${DISK}..."
    P2_END=$(sfdisk -l "${DISK}" 2>/dev/null | grep "${DISK}p2" | awk '{print $3}')
    if [ -z "${P2_END}" ] || [ "${P2_END}" -le 0 ] 2>/dev/null; then
        echo "setup-data: cannot determine end of p2, aborting"
        exit 1
    fi
    P3_START=$((P2_END + 1))
    echo "${P3_START},," | sfdisk --force --append "${DISK}" 2>/dev/null
    partprobe "${DISK}" 2>/dev/null || true
    udevadm settle --timeout=10 2>/dev/null || sleep 3

    if [ ! -b "${DEVICE}" ]; then
        echo "setup-data: ${DEVICE} not present after create"
        exit 1
    fi
fi

# Format as f2fs
echo "setup-data: formatting ${DEVICE} as f2fs..."
mkfs.f2fs -f -l data "${DEVICE}"

# Mount
mount -t f2fs -o noatime "${DEVICE}" /data
echo "setup-data: done"
SETUPSCRIPT
chmod +x /usr/local/sbin/setup-data-partition.sh

cat > /etc/systemd/system/setup-data-partition.service << 'EOF'
[Unit]
Description=Setup /data partition (create, format, mount)
After=local-fs.target systemd-udevd.service
Before=network-pre.target zeclock.service wifi-connect.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/setup-data-partition.sh
RemainAfterExit=yes
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
EOF
systemctl enable setup-data-partition.service

# ==========================================================================
# 4. Init /data directory structure
# ==========================================================================

cat > /usr/local/sbin/init-data-partition.sh << 'INITDATA'
#!/bin/bash
# Initialize /data directory structure after mount.
set -e

DATA="/data"
if ! mountpoint -q "${DATA}" 2>/dev/null; then
    exit 0
fi

# Skip if already initialized
[ -f "${DATA}/.initialized" ] && exit 0

# Create structure
mkdir -p "${DATA}/zeclock/config"
mkdir -p "${DATA}/zeclock/logs"
mkdir -p "${DATA}/zeclock/state"
mkdir -p "${DATA}/networkmanager/system-connections"
mkdir -p "${DATA}/ssh"

# Copy default config if none exists
if [ ! -f "${DATA}/zeclock/config/zeclock.ini" ]; then
    cp /overlay/lower/home/zeclock/.zeclock/config/zeclock.ini "${DATA}/zeclock/config/" 2>/dev/null || \
    cp /home/zeclock/.zeclock/config/zeclock.ini "${DATA}/zeclock/config/" 2>/dev/null || true
fi

# Copy SSH host keys
if [ ! -f "${DATA}/ssh/ssh_host_ed25519_key" ]; then
    cp /overlay/lower/etc/ssh/ssh_host_*_key* "${DATA}/ssh/" 2>/dev/null || \
    cp /etc/ssh/ssh_host_*_key* "${DATA}/ssh/" 2>/dev/null || true
fi

chown -R zeclock:zeclock "${DATA}/zeclock"
chmod 700 "${DATA}/ssh"
find "${DATA}/ssh" -type f -exec chmod 600 {} \; 2>/dev/null || true

touch "${DATA}/.initialized"
echo "init-data: done"
INITDATA
chmod +x /usr/local/sbin/init-data-partition.sh

cat > /etc/systemd/system/init-data-partition.service << 'EOF'
[Unit]
Description=Initialize /data partition structure
After=setup-data-partition.service
Requires=setup-data-partition.service
Before=NetworkManager.service zeclock.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/init-data-partition.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl enable init-data-partition.service

# ==========================================================================
# 5. Bind-mount persistent dirs from /data
# ==========================================================================

cat > /usr/local/sbin/bind-persistent-dirs.sh << 'BINDSCRIPT'
#!/bin/bash
# Bind-mount persistent directories from /data.
set -e

DATA="/data"
if ! mountpoint -q "${DATA}" 2>/dev/null; then
    exit 0
fi

# NetworkManager connections
if [ -d "${DATA}/networkmanager/system-connections" ]; then
    mount --bind "${DATA}/networkmanager/system-connections" /etc/NetworkManager/system-connections 2>/dev/null || true
fi

# SSH host keys
if [ -d "${DATA}/ssh" ] && [ -f "${DATA}/ssh/ssh_host_ed25519_key" ]; then
    for key in "${DATA}"/ssh/ssh_host_*; do
        base=$(basename "${key}")
        [ -f "/etc/ssh/${base}" ] && mount --bind "${key}" "/etc/ssh/${base}" 2>/dev/null || true
    done
fi

echo "bind-persistent: done"
BINDSCRIPT
chmod +x /usr/local/sbin/bind-persistent-dirs.sh

cat > /etc/systemd/system/bind-persistent-dirs.service << 'EOF'
[Unit]
Description=Bind-mount persistent directories from /data
After=init-data-partition.service
Requires=init-data-partition.service
Before=NetworkManager.service sshd.service ssh.service zeclock.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bind-persistent-dirs.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl enable bind-persistent-dirs.service

# ==========================================================================
# 6. Bash helpers
# ==========================================================================

cat >> /etc/bash.bashrc << 'BASHRC'

# Overlay filesystem helpers
# To make persistent changes to the root filesystem:
#   sudo chroot /overlay/lower
# Or add "skipoverlay" to /boot/firmware/cmdline.txt and reboot
set_bash_prompt(){
    if mount | grep -q "overlay on / "; then
        fs_mode="ro"
    else
        fs_mode="rw"
    fi
    PS1='\[\033[01;32m\]\u@\h(${fs_mode})\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
}
PROMPT_COMMAND=set_bash_prompt
BASHRC

echo ">>> Overlay filesystem setup complete."
echo "    Root is protected via initramfs overlayfs."
echo "    Writes go to RAM (tmpfs), SD card is read-only."
echo "    Persistent data on /data (f2fs, created on first boot)."
echo "    Add 'skipoverlay' to cmdline.txt to disable for maintenance."
