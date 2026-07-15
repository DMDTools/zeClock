"""ZeDMD WiFi auto-discovery module.

Discovers ZeDMD devices on the local network using mDNS (multicast DNS).
The ZeDMD firmware advertises itself as 'zedmd-wifi.local' via mDNS.
"""

import logging
import socket
import threading
from dataclasses import dataclass, field
from typing import List, Optional

import urllib.request
import json

logger = logging.getLogger(__name__)

ZEDMD_MDNS_HOSTNAME = "zedmd-wifi.local"
ZEDMD_HTTP_TIMEOUT = 3  # seconds


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
                "result": (
                    {
                        "ip": self.result.ip,
                        "port": self.result.port,
                        "version": self.result.version,
                    }
                    if self.result
                    else None
                ),
            }


def resolve_mdns(hostname: str) -> Optional[str]:
    """Resolve an mDNS hostname to an IP address.

    Uses the system resolver (avahi on Linux) to resolve .local hostnames.

    Args:
        hostname: The mDNS hostname to resolve (e.g. 'zedmd-wifi.local').

    Returns:
        IP address string, or None if resolution fails.
    """
    try:
        results = socket.getaddrinfo(hostname, 80, socket.AF_INET, socket.SOCK_STREAM)
        if results:
            # results[0] = (family, type, proto, canonname, (ip, port))
            ip: str = str(results[0][4][0])
            return ip
    except (socket.gaierror, OSError, IndexError):
        pass
    return None


def probe_zedmd(ip: str) -> Optional[DiscoveryResult]:
    """Probe an IP to check if it's a ZeDMD (HTTP API on port 80)."""
    try:
        # Check /get_version
        req = urllib.request.Request(
            f"http://{ip}/get_version", headers={"User-Agent": "zeClock-Discovery"}
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
                headers={"User-Agent": "zeClock-Discovery"},
            )
            with urllib.request.urlopen(req, timeout=ZEDMD_HTTP_TIMEOUT) as resp:
                config = json.loads(resp.read())
                port = config.get("port", 3333)
        except Exception:
            pass

        return DiscoveryResult(ip=ip, port=port, version=version)

    except Exception:
        return None


def discover_zedmd(
    state: Optional[DiscoveryState] = None,
) -> Optional[DiscoveryResult]:
    """Discover ZeDMD on the local network via mDNS.

    The ZeDMD firmware advertises itself as 'zedmd-wifi.local'.
    This function resolves that hostname and probes the HTTP API.

    Args:
        state: Optional DiscoveryState to track progress (for UI updates).

    Returns:
        DiscoveryResult if found, None otherwise.
    """
    if state is None:
        state = DiscoveryState()

    state.update("scanning", "Resolving ZeDMD via mDNS (zedmd-wifi.local)...")

    ip = resolve_mdns(ZEDMD_MDNS_HOSTNAME)
    if not ip:
        state.update("not_found", "mDNS resolution failed for zedmd-wifi.local")
        return None

    state.update("probing", f"Found {ZEDMD_MDNS_HOSTNAME} at {ip}, probing...")

    result = probe_zedmd(ip)
    if result:
        state.result = result
        state.update("found", f"ZeDMD v{result.version} found at {ip}:{result.port}")
        return result

    state.update("not_found", f"Host {ip} did not respond as ZeDMD")
    return None
