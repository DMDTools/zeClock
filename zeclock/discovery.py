"""ZeDMD WiFi auto-discovery module.

Discovers ZeDMD devices on the local network by:
1. Scanning ARP table for Espressif MAC prefixes (ESP32-based devices)
2. Probing candidates on port 80 for the ZeDMD HTTP API (/get_version)
3. Retrieving connection config (/get_config) to get the streaming port
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import urllib.request
import json

logger = logging.getLogger(__name__)

# Known Espressif MAC prefixes (OUI)
ESPRESSIF_MAC_PREFIXES = [
    "08:d1:f9", "dc:4f:22", "24:0a:c4", "a4:cf:12",
    "ac:67:b2", "bc:dd:c2", "c8:f0:9e", "ec:fa:bc",
    "30:ae:a4", "24:6f:28", "a0:20:a6", "10:52:1c",
    "e8:68:e7", "84:f7:03", "3c:71:bf", "f0:08:d1",
    "48:e7:29", "54:43:b2", "d8:bf:c0", "7c:df:a1",
    "cc:50:e3", "70:b8:f6", "08:3a:f2", "40:f5:20",
]

ZEDMD_HTTP_TIMEOUT = 2  # seconds


@dataclass
class DiscoveryResult:
    """Result of a ZeDMD discovery attempt."""
    ip: str
    port: int = 3333
    version: str = ""
    mac: str = ""


@dataclass
class DiscoveryState:
    """Observable state of the discovery process."""
    status: str = "idle"  # idle, scanning, probing, found, not_found
    message: str = ""
    steps: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)
    result: Optional[DiscoveryResult] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, status: str, message: str) -> None:
        with self._lock:
            self.status = status
            self.message = message
            self.steps.append(message)
            logger.info(f"[discovery] {message}")

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "message": self.message,
                "steps": list(self.steps),
                "candidates": list(self.candidates),
                "result": {
                    "ip": self.result.ip,
                    "port": self.result.port,
                    "version": self.result.version,
                } if self.result else None,
            }


def get_arp_table() -> List[dict]:
    """Parse /proc/net/arp for IP/MAC entries."""
    entries = []
    try:
        with open("/proc/net/arp", "r") as f:
            lines = f.readlines()[1:]  # skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[0]
                mac = parts[3].lower()
                if mac != "00:00:00:00:00:00":
                    entries.append({"ip": ip, "mac": mac})
    except (OSError, IndexError):
        pass
    return entries


def ping_sweep(subnet: str, count: int = 1) -> None:
    """Quick ping sweep to populate ARP table."""
    # Use a fast broadcast ping to populate ARP cache
    try:
        subprocess.run(
            ["ping", "-b", "-c", str(count), "-W", "1", f"{subnet}.255"],
            capture_output=True, timeout=3
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Also try individual pings on common DHCP ranges (faster than full /24)
    # This helps if broadcast ping is blocked
    try:
        for i in range(1, 50):
            subprocess.Popen(
                ["ping", "-c", "1", "-W", "1", f"{subnet}.{i}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        time.sleep(1.5)
    except (FileNotFoundError, OSError):
        pass


def get_local_subnet() -> Optional[str]:
    """Get the local subnet (e.g. '192.168.0') from the default route."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5
        )
        # Example: "default via 192.168.0.1 dev wlan0 ..."
        parts = result.stdout.split()
        if "via" in parts:
            gateway = parts[parts.index("via") + 1]
            # Return the first 3 octets
            octets = gateway.split(".")
            if len(octets) == 4:
                return ".".join(octets[:3])
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def probe_zedmd(ip: str) -> Optional[DiscoveryResult]:
    """Probe an IP to check if it's a ZeDMD (HTTP API on port 80)."""
    try:
        # Check /get_version
        req = urllib.request.Request(
            f"http://{ip}/get_version",
            headers={"User-Agent": "zeClock-Discovery"}
        )
        with urllib.request.urlopen(req, timeout=ZEDMD_HTTP_TIMEOUT) as resp:
            version = resp.read().decode("utf-8", errors="replace").strip()

        if not version or len(version) > 20:
            return None

        # Get config for port number
        port = 3333
        try:
            req = urllib.request.Request(
                f"http://{ip}/get_config",
                headers={"User-Agent": "zeClock-Discovery"}
            )
            with urllib.request.urlopen(req, timeout=ZEDMD_HTTP_TIMEOUT) as resp:
                config = json.loads(resp.read())
                port = config.get("port", 3333)
        except Exception:
            pass

        return DiscoveryResult(ip=ip, port=port, version=version)

    except Exception:
        return None


def discover_zedmd(state: Optional[DiscoveryState] = None) -> Optional[DiscoveryResult]:
    """Run the full ZeDMD WiFi discovery process.

    Args:
        state: Optional DiscoveryState to track progress (for UI updates).

    Returns:
        DiscoveryResult if found, None otherwise.
    """
    if state is None:
        state = DiscoveryState()

    state.update("scanning", "Scanning local network for ZeDMD devices...")

    # Get local subnet
    subnet = get_local_subnet()
    if not subnet:
        state.update("not_found", "Could not determine local subnet")
        return None

    state.update("scanning", f"Network subnet: {subnet}.0/24")

    # Ping sweep to populate ARP table
    state.update("scanning", "Populating ARP table (ping sweep)...")
    ping_sweep(subnet)

    # Check ARP table for Espressif devices
    arp_entries = get_arp_table()
    candidates = []
    for entry in arp_entries:
        mac_prefix = entry["mac"][:8]
        if mac_prefix in ESPRESSIF_MAC_PREFIXES:
            candidates.append(entry["ip"])

    if not candidates:
        # No Espressif devices found — try probing all ARP entries
        state.update("scanning", "No Espressif devices in ARP table, probing all known hosts...")
        candidates = [e["ip"] for e in arp_entries if e["ip"] != "0.0.0.0"]

    state.candidates = candidates
    state.update("probing", f"Found {len(candidates)} candidate(s) to probe")

    # Probe each candidate
    for ip in candidates:
        state.update("probing", f"Probing {ip}...")
        result = probe_zedmd(ip)
        if result:
            state.result = result
            state.update("found", f"ZeDMD v{result.version} found at {ip}:{result.port}")
            return result

    state.update("not_found", "No ZeDMD found on the network")
    return None
