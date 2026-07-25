"""Reolink Alert Plugin - Intrusion detection alerts from Reolink cameras.

Connects to a Reolink camera via the reolink_aio library (Baichuan TCP
push protocol) to receive real-time AI detection events. When a person,
vehicle, animal, or motion is detected, a blinking alert message is
displayed on the DMD to attract attention.

Each detection type shows a different localized message and color:
  - Person: red blinking border
  - Vehicle: orange blinking border
  - Animal: green blinking border
  - Motion: yellow blinking border

The border blinks to draw attention. The alert remains visible for a
configurable duration (default 15 seconds), then the clock resumes
normal rotation.

Requires: uv sync --extra reolink
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from PIL import Image

from .base import ClockPlugin, ConfigField, PluginNotConfiguredError

logger = logging.getLogger(__name__)

# Alert display duration in seconds
DEFAULT_ALERT_DURATION = 15

# Blink interval in frames (toggle every N frames at ~10 FPS)
BLINK_INTERVAL_FRAMES = 5

# Localized alert messages per detection type
# Each detection type has a border color and messages in supported languages
_ALERT_MESSAGES: Dict[str, Dict[str, str]] = {
    "person": {
        "en": "PERSON\nDETECTED",
        "fr": "PERSONNE\nDETECTEE",
        "de": "PERSON\nERKANNT",
        "es": "PERSONA\nDETECTADA",
    },
    "vehicle": {
        "en": "VEHICLE\nDETECTED",
        "fr": "VEHICULE\nDETECTE",
        "de": "FAHRZEUG\nERKANNT",
        "es": "VEHICULO\nDETECTADO",
    },
    "dog_cat": {
        "en": "ANIMAL\nDETECTED",
        "fr": "ANIMAL\nDETECTE",
        "de": "TIER\nERKANNT",
        "es": "ANIMAL\nDETECTADO",
    },
    "motion": {
        "en": "MOTION\nDETECTED",
        "fr": "MOUVEMENT\nDETECTE",
        "de": "BEWEGUNG\nERKANNT",
        "es": "MOVIMIENTO\nDETECTADO",
    },
}

# Border colors per detection type
_BORDER_COLORS: Dict[str, Tuple[int, int, int]] = {
    "person": (255, 0, 0),  # Red
    "vehicle": (255, 128, 0),  # Orange
    "dog_cat": (0, 200, 0),  # Green
    "motion": (255, 255, 0),  # Yellow
}

# Priority order: higher priority detection types override lower ones
DETECTION_PRIORITY = ["person", "vehicle", "dog_cat", "motion"]


class ReolinkAlertPlugin(ClockPlugin):
    """Reolink camera intrusion alert plugin.

    Connects to a Reolink camera using the Baichuan protocol for
    real-time push event detection. When a person, vehicle, animal,
    or motion is detected, triggers a rich alert via /api/alert
    (blinking border + icon + wrapped text).

    This plugin is non-rotatable — it runs as a background listener
    and never participates in display rotation.
    """

    def __init__(self) -> None:
        """Initialize with empty state."""
        self._helpers: Any = None
        self._host: Any = None  # reolink_aio Host instance
        self._listener_task: Optional[asyncio.Task] = None
        self._camera_host: str = ""
        self._camera_user: str = ""
        self._camera_password: str = ""
        self._camera_channel: int = 0
        self._connected: bool = False
        self._rest_port: int = 8080
        self._language: str = "en"
        self._alert_duration: int = DEFAULT_ALERT_DURATION
        # Keep track of last alert to avoid re-triggering too fast
        self._last_alert_time: float = 0.0
        self._cooldown_seconds: int = 10

    @property
    def name(self) -> str:
        return "reolink-alert"

    @property
    def description(self) -> str:
        return "Intrusion alerts from Reolink camera (person/vehicle/animal/motion)"

    @property
    def frame_delay_ms(self) -> int:
        return 100  # 10 FPS for smooth blinking

    @property
    def rotatable(self) -> bool:
        # This plugin does NOT participate in normal rotation.
        # It activates itself when an alert is triggered.
        return False

    @property
    def config_schema(self) -> List[ConfigField]:
        """Configuration fields for the Web UI."""
        return [
            ConfigField(
                "camera_host",
                "Camera IP/Host",
                "text",
                required=True,
                description="IP address or hostname of the Reolink camera",
            ),
            ConfigField(
                "camera_user",
                "Username",
                "text",
                required=True,
                description="Camera login username",
                default="admin",
            ),
            ConfigField(
                "camera_password",
                "Password",
                "password",
                required=True,
                description="Camera login password",
            ),
            ConfigField(
                "camera_channel",
                "Channel",
                "number",
                required=False,
                description="Camera channel (0 for single camera, 0+ for NVR)",
                default="0",
            ),
            ConfigField(
                "alert_duration",
                "Alert Duration (seconds)",
                "number",
                required=False,
                description="How long to display the alert (5-60 seconds)",
                default="15",
            ),
            ConfigField(
                "cooldown_seconds",
                "Cooldown (seconds)",
                "number",
                required=False,
                description="Minimum time between alerts (prevents spam)",
                default="10",
            ),
        ]

    def _get_message(self, detection_type: str) -> str:
        """Get the localized alert message for a detection type."""
        messages = _ALERT_MESSAGES.get(detection_type, _ALERT_MESSAGES["motion"])
        return messages.get(self._language, messages["en"])

    async def initialize(self, config: dict) -> None:
        """Initialize the plugin and connect to the Reolink camera.

        Config keys:
            camera_host (str): IP or hostname of the camera.
            camera_user (str): Login username.
            camera_password (str): Login password.
            camera_channel (int): Channel index (default 0).
            alert_duration (int): Alert display duration in seconds.
            cooldown_seconds (int): Minimum time between alerts.
            language (str): Display language (en/fr/de/es).

        Raises:
            PluginNotConfiguredError: If required camera credentials are missing.
        """
        self._helpers = config.get("_helpers")

        # Language (injected globally by PluginConfig)
        lang = config.get("language", "en")
        self._language = lang if lang in ("en", "fr", "de", "es") else "en"

        # Extract camera configuration
        self._camera_host = config.get("camera_host", "").strip()
        self._camera_user = config.get("camera_user", "admin").strip()
        self._camera_password = config.get("camera_password", "").strip()

        if not self._camera_host or not self._camera_password:
            raise PluginNotConfiguredError(
                "Reolink camera host and password are required"
            )

        try:
            self._camera_channel = int(config.get("camera_channel", 0))
        except (ValueError, TypeError):
            self._camera_channel = 0

        try:
            self._alert_duration = max(
                5, min(60, int(config.get("alert_duration", DEFAULT_ALERT_DURATION)))
            )
        except (ValueError, TypeError):
            self._alert_duration = DEFAULT_ALERT_DURATION

        try:
            self._cooldown_seconds = max(
                5, min(120, int(config.get("cooldown_seconds", 10)))
            )
        except (ValueError, TypeError):
            self._cooldown_seconds = 10

        # REST API port (for triggering text overlay alerts)
        try:
            self._rest_port = int(config.get("rest_port", 8080))
        except (ValueError, TypeError):
            self._rest_port = 8080

        # Start background connection and event listener (only if not already running)
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._run_listener())

    async def _run_listener(self) -> None:
        """Background task: connect to camera and listen for events."""
        try:
            from reolink_aio.api import Host
        except ImportError:
            logger.error(
                "reolink-aio not installed. Install with: uv sync --extra reolink\n"
                "Reolink alert plugin disabled."
            )
            return

        retry_delay = 5.0

        while True:
            try:
                logger.info("Connecting to Reolink camera at %s...", self._camera_host)
                self._host = Host(
                    host=self._camera_host,
                    username=self._camera_user,
                    password=self._camera_password,
                )

                # Connect and get device info
                await self._host.get_host_data()
                self._connected = True
                logger.info(
                    "Connected to Reolink camera: %s (%s)",
                    self._host.nvr_name,
                    self._host.mac_address,
                )

                # Register callback for push events
                self._host.baichuan.register_callback("zeclock_alert", self._on_event)

                # Subscribe to TCP push events
                await self._host.baichuan.subscribe_events()
                logger.info("Subscribed to Reolink Baichuan push events")

                # Keep connection alive — reset retry delay on success
                retry_delay = 5.0
                while self._connected:
                    await asyncio.sleep(30)

            except asyncio.CancelledError:
                logger.info("Reolink listener task cancelled")
                break
            except Exception as e:
                logger.warning(
                    "Reolink connection error: %s. Retrying in %.0fs...",
                    e,
                    retry_delay,
                )
                self._connected = False
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 60.0)

    def _on_event(self) -> None:
        """Callback invoked by reolink_aio when a push event is received.

        The Host object's state is updated before this callback fires.
        We check which detection types are active and trigger an alert
        for the highest-priority one.

        Since this callback is synchronous, we schedule the async alert
        trigger on the running event loop.
        """
        if self._host is None:
            return

        now = time.time()
        ch = self._camera_channel

        # Log every event for debugging
        motion = False
        ai_states = {}
        try:
            motion = self._host.motion_detected(ch)
        except Exception:
            pass
        for det in ("person", "vehicle", "dog_cat"):
            try:
                ai_states[det] = self._host.ai_detected(ch, det)
            except Exception:
                ai_states[det] = None

        logger.info(
            "Reolink push event (ch=%d): motion=%s, ai=%s",
            ch,
            motion,
            ai_states,
        )

        # Cooldown: don't trigger too frequently
        if now - self._last_alert_time < self._cooldown_seconds:
            return

        # Check AI detection states (person > vehicle > animal > motion)
        ch = self._camera_channel
        detected_type: Optional[str] = None

        for det_type in DETECTION_PRIORITY:
            try:
                if det_type == "motion":
                    if self._host.motion_detected(ch):
                        detected_type = "motion"
                        break
                else:
                    if self._host.ai_detected(ch, det_type):
                        detected_type = det_type
                        break
            except Exception:
                # Some detection types may not be supported by the camera
                continue

        if detected_type is None:
            return

        logger.info("Reolink alert triggered: %s detected", detected_type)
        self._last_alert_time = now

        # Schedule async alert trigger on the running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._trigger_alert_display(detected_type))
        except RuntimeError:
            logger.debug("No running event loop for alert trigger")

    async def _trigger_alert_display(self, detected_type: str) -> None:
        """Trigger a rich alert display via the /api/alert endpoint.

        Sends an HTTP request to display the alert with blinking border,
        detection-specific icon, and localized text.
        """
        text = self._get_message(detected_type).replace("\n", " ")
        icon_map = {
            "person": "person",
            "vehicle": "vehicle",
            "dog_cat": "animal",
            "motion": "motion",
        }
        icon = icon_map.get(detected_type, "beacon")
        color = list(_BORDER_COLORS.get(detected_type, (255, 0, 0)))

        try:
            url = f"http://127.0.0.1:{self._rest_port}/api/alert"
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={
                        "text": text,
                        "duration": self._alert_duration,
                        "icon": icon,
                        "color": color,
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        logger.debug("Alert triggered: %s (%s)", text, icon)
                    else:
                        logger.warning("Failed to trigger alert: HTTP %d", resp.status)
        except Exception as e:
            logger.warning("Could not trigger alert via REST API: %s", e)

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render a status screen (plugin is background-only).

        This is only called if the plugin is force-activated via the Web UI.
        Since the plugin is a background listener, just show connection status.
        """
        if self._helpers:
            status = "CONNECTED" if self._connected else "CONNECTING..."
            return self._helpers.render_text(
                f"REOLINK\n{status}",
                color=(0, 128, 255) if self._connected else (128, 128, 128),
                centered=True,
            )
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        """No-op: the background listener keeps running independently."""
        pass
