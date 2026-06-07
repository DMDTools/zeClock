"""WiFi setup module for zeClock.

When no WiFi is configured, creates a hotspot AP and serves a captive portal
web page that lets users select and connect to a WiFi network.

Replaces balena wifi-connect with a pure Python + NetworkManager solution.

Usage:
    python -m zeclock.wifi_setup

Flow:
    1. Check if WiFi is connected (iwgetid)
    2. If connected → exit (nothing to do)
    3. Create a hotspot AP via nmcli
    4. Start a web server on the AP interface
    5. Serve a page listing available networks
    6. User selects network + enters password
    7. Connect to the selected network via nmcli
    8. If successful → tear down AP and exit
    9. If failed → show error, let user retry
"""

import asyncio
import logging
import subprocess
import sys
import time
from typing import List, Tuple

from aiohttp import web

logger = logging.getLogger(__name__)

AP_SSID = "zeClockSetup"
AP_PASSWORD = "zeclock1"  # WPA2 minimum 8 chars
AP_IP = "10.42.0.1"
AP_INTERFACE = "wlan0"
WEB_PORT = 80
CONNECTION_NAME = "zeclock-hotspot"


def is_wifi_connected() -> bool:
    """Check if WiFi is currently connected to a network."""
    try:
        result = subprocess.run(
            ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_wifi_interface() -> str:
    """Get the WiFi interface name."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "wifi":
                return parts[0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return AP_INTERFACE


def scan_networks() -> List[dict]:
    """Scan for available WiFi networks."""
    try:
        # Trigger a rescan
        subprocess.run(
            ["nmcli", "device", "wifi", "rescan"], capture_output=True, timeout=10
        )
        time.sleep(2)
        # Get results
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        networks: List[dict] = []
        seen: set = set()
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                ssid = parts[0].strip()
                if ssid and ssid not in seen and ssid != AP_SSID:
                    seen.add(ssid)
                    signal = int(parts[1]) if parts[1].isdigit() else 0
                    networks.append(
                        {
                            "ssid": ssid,
                            "signal": signal,
                            "security": parts[2] if len(parts) > 2 else "",
                        }
                    )
        # Sort by signal strength
        networks.sort(key=lambda x: x.get("signal", 0), reverse=True)
        return networks
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def create_hotspot() -> bool:
    """Create a WiFi hotspot using NetworkManager."""
    logger.info(f"Creating hotspot AP '{AP_SSID}' on {AP_INTERFACE}...")

    # Remove existing hotspot connection if any
    subprocess.run(
        ["nmcli", "connection", "delete", CONNECTION_NAME],
        capture_output=True,
        timeout=10,
    )

    # Use 'nmcli dev wifi hotspot' — the reliable method on Pi 4 Bookworm
    cmd = [
        "nmcli",
        "dev",
        "wifi",
        "hotspot",
        "ifname",
        AP_INTERFACE,
        "ssid",
        AP_SSID,
        "password",
        AP_PASSWORD,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        logger.error(f"Failed to create hotspot: {result.stderr}")
        return False

    logger.info(f"Hotspot '{AP_SSID}' active (password: {AP_PASSWORD})")
    return True


def teardown_hotspot() -> None:
    """Remove the hotspot."""
    subprocess.run(
        ["nmcli", "connection", "down", "Hotspot"],
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["nmcli", "connection", "delete", "Hotspot"],
        capture_output=True,
        timeout=10,
    )
    logger.info("Hotspot removed")


def connect_to_network(ssid: str, password: str) -> Tuple[bool, str]:
    """Connect to a WiFi network. Returns (success, message)."""
    logger.info(f"Connecting to '{ssid}'...")

    # First tear down the hotspot
    teardown_hotspot()
    time.sleep(2)

    # Try to connect
    cmd = [
        "nmcli",
        "device",
        "wifi",
        "connect",
        ssid,
        "password",
        password,
        "ifname",
        AP_INTERFACE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode == 0:
        logger.info(f"Connected to '{ssid}'")
        return True, f"Connected to {ssid}"
    else:
        error = result.stderr.strip() or "Connection failed"
        logger.warning(f"Failed to connect to '{ssid}': {error}")
        # Re-create hotspot so user can retry
        create_hotspot()
        return False, error


# --- Web server ---

PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>zeClock WiFi Setup</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0;
               min-height: 100vh; padding: 1rem; display: flex; flex-direction: column; align-items: center; }
        h1 { color: #ff8800; margin: 1rem 0; font-size: 1.5rem; }
        .card { background: #16213e; border-radius: 12px; padding: 1.5rem; width: 100%;
                max-width: 400px; margin: 0.5rem 0; }
        .network { padding: 0.75rem; margin: 0.3rem 0; background: #0f3460; border-radius: 8px;
                   cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
        .network:hover { background: #1a4a8a; }
        .network .ssid { font-weight: bold; }
        .network .meta { font-size: 0.8rem; color: #888; }
        input[type="password"], input[type="text"] { width: 100%; padding: 0.75rem; margin: 0.5rem 0;
               background: #0f3460; border: 1px solid #2a3a5e; border-radius: 8px; color: #e0e0e0; font-size: 1rem; }
        button { width: 100%; padding: 0.75rem; margin: 0.5rem 0; border: none; border-radius: 8px;
                 font-size: 1rem; cursor: pointer; font-weight: bold; }
        .btn-connect { background: #ff8800; color: #000; }
        .btn-scan { background: #455a64; color: #e0e0e0; }
        .status { padding: 0.75rem; border-radius: 8px; margin: 0.5rem 0; text-align: center; }
        .status.success { background: #1b5e20; }
        .status.error { background: #b71c1c; }
        .loading { text-align: center; color: #888; padding: 2rem; }
        #password-form { display: none; }
    </style>
</head>
<body>
    <h1>🕒 zeClock WiFi Setup</h1>

    <div class="card">
        <div id="network-list"><div class="loading">Scanning networks...</div></div>
        <button class="btn-scan" onclick="scanNetworks()">🔄 Refresh</button>
    </div>

    <div class="card" id="password-form">
        <p>Connect to: <strong id="selected-ssid"></strong></p>
        <input type="password" id="wifi-password" placeholder="WiFi password">
        <button class="btn-connect" onclick="connectWifi()">Connect</button>
        <button class="btn-scan" onclick="cancelConnect()">Cancel</button>
    </div>

    <div class="card" id="status-card" style="display:none">
        <div id="status-msg" class="status"></div>
    </div>

    <script>
    let selectedSsid = '';

    async function scanNetworks() {
        document.getElementById('network-list').innerHTML = '<div class="loading">Scanning...</div>';
        const resp = await fetch('/api/networks');
        const data = await resp.json();
        const list = document.getElementById('network-list');
        if (!data.networks || data.networks.length === 0) {
            list.innerHTML = '<div class="loading">No networks found</div>';
            return;
        }
        list.innerHTML = data.networks.map(n =>
            `<div class="network" onclick="selectNetwork('${n.ssid.replace(/'/g, "\\'")}')">
                <span class="ssid">${n.ssid}</span>
                <span class="meta">${n.signal}% ${n.security ? '🔒' : ''}</span>
            </div>`
        ).join('');
    }

    function selectNetwork(ssid) {
        selectedSsid = ssid;
        document.getElementById('selected-ssid').textContent = ssid;
        document.getElementById('password-form').style.display = 'block';
        document.getElementById('wifi-password').focus();
    }

    function cancelConnect() {
        document.getElementById('password-form').style.display = 'none';
        selectedSsid = '';
    }

    async function connectWifi() {
        const password = document.getElementById('wifi-password').value;
        showStatus('Connecting...', '');
        const resp = await fetch('/api/connect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ssid: selectedSsid, password: password})
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('password-form').style.display = 'none';
            showStatus('✅ ' + data.message, 'success');
            startRedirectCountdown();
        } else {
            showStatus('❌ ' + data.message, 'error');
            scanNetworks();
        }
    }

    function showStatus(msg, cls) {
        const card = document.getElementById('status-card');
        const el = document.getElementById('status-msg');
        card.style.display = 'block';
        el.textContent = msg;
        el.className = 'status ' + cls;
    }

    document.getElementById('wifi-password').addEventListener('keydown', e => {
        if (e.key === 'Enter') connectWifi();
    });

    scanNetworks();

    function startRedirectCountdown() {
        let seconds = 10;
        const interval = setInterval(() => {
            seconds--;
            showStatus('✅ Connected! Starting zeClock... Redirecting in ' + seconds + 's', 'success');
            if (seconds <= 0) {
                clearInterval(interval);
                window.location.href = 'http://zeclock.local:8080';
            }
        }, 1000);
    }
    </script>
</body>
</html>"""


class WifiSetupServer:
    """Captive portal web server for WiFi configuration."""

    # URLs used by devices to detect captive portals
    CAPTIVE_PORTAL_CHECKS = [
        "/hotspot-detect.html",        # Apple iOS/macOS
        "/library/test/success.html",   # Apple
        "/generate_204",               # Android
        "/gen_204",                    # Android
        "/connecttest.txt",            # Windows
        "/ncsi.txt",                   # Windows
        "/redirect",                   # Windows 11
    ]

    def __init__(self) -> None:
        self._app = web.Application()
        self._pending_connect: bool = False

        # Captive portal detection endpoints — must return redirect/non-success
        for path in self.CAPTIVE_PORTAL_CHECKS:
            self._app.router.add_get(path, self._handle_captive_check)

        self._app.router.add_get("/", self._handle_portal)
        self._app.router.add_get("/api/networks", self._handle_scan)
        self._app.router.add_post("/api/connect", self._handle_connect)
        # Catch-all — redirect to portal
        self._app.router.add_get("/{path:.*}", self._handle_captive_check)

    async def _handle_captive_check(self, request: web.Request) -> web.Response:
        """Respond to captive portal detection — redirect to our portal page."""
        raise web.HTTPFound(f"http://{AP_IP}/")

    async def _handle_portal(self, request: web.Request) -> web.Response:
        return web.Response(text=PORTAL_HTML, content_type="text/html")

    async def _handle_scan(self, request: web.Request) -> web.Response:
        networks = await asyncio.get_event_loop().run_in_executor(None, scan_networks)
        return web.json_response({"networks": networks})

    async def _handle_connect(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"success": False, "message": "Invalid request"}, status=400
            )

        ssid = body.get("ssid", "")
        password = body.get("password", "")

        if not ssid:
            return web.json_response(
                {"success": False, "message": "No SSID provided"}, status=400
            )

        # Return success immediately — the JS will show countdown
        # Then connect in background (hotspot stays up for a few seconds)
        asyncio.get_event_loop().call_later(
            3, lambda: asyncio.ensure_future(self._do_connect(ssid, password))
        )

        return web.json_response(
            {"success": True, "message": f"Connecting to {ssid}..."}
        )

    async def _do_connect(self, ssid: str, password: str) -> None:
        """Connect to WiFi in background after response was sent."""
        success, message = await asyncio.get_event_loop().run_in_executor(
            None, connect_to_network, ssid, password
        )
        if success:
            # Give client time to see the redirect message, then exit
            await asyncio.sleep(5)
            self._shutdown()
        # If failed, hotspot was re-created by connect_to_network

    def _shutdown(self) -> None:
        """Stop the event loop to exit."""
        asyncio.get_event_loop().stop()

    async def run(self) -> None:
        runner = web.AppRunner(self._app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
        await site.start()
        logger.info(f"WiFi setup portal running on http://{AP_IP}:{WEB_PORT}")
        print(f"🌐 WiFi setup portal on http://{AP_IP}:{WEB_PORT}")
        # Run until stopped
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()


def main() -> None:
    """Entry point for wifi-setup mode."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("🔍 Checking WiFi connection...")

    # Wait a bit for NetworkManager to settle
    time.sleep(5)

    if is_wifi_connected():
        ssid = subprocess.run(
            ["iwgetid", "-r"], capture_output=True, text=True
        ).stdout.strip()
        print(f"✅ Already connected to '{ssid}' — nothing to do")
        sys.exit(0)

    print("📡 No WiFi connection — starting setup portal...")

    # Enable WiFi radio via NetworkManager
    subprocess.run(["nmcli", "r", "wifi", "on"], capture_output=True, timeout=10)
    time.sleep(2)

    if not create_hotspot():
        print("❌ Failed to create hotspot AP")
        sys.exit(1)

    print(f"📶 Connect to WiFi '{AP_SSID}' (password: {AP_PASSWORD})")
    print(f"   Then open http://{AP_IP} to configure your network")

    # Run the web server
    server = WifiSetupServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
    finally:
        teardown_hotspot()

    print("✅ WiFi setup complete")


if __name__ == "__main__":
    main()
