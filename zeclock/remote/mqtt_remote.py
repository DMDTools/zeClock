"""MQTT remote control for zeClock.

Provides bidirectional MQTT communication:
- Subscribes to command topics for remote control
- Publishes state updates (active plugin, brightness, screen state)
- Supports Home Assistant MQTT Discovery for auto-created entities
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from .command_handler import CommandHandler

logger = logging.getLogger(__name__)


@dataclass
class MqttConfig:
    """MQTT connection configuration."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    device_id: str = "zeclock"
    topic_prefix: str = "zeclock"
    ha_discovery: bool = True
    ha_discovery_prefix: str = "homeassistant"
    state_interval: float = 30.0  # seconds between state publishes


class MqttRemote:
    """MQTT client for zeClock remote control.

    Runs as an asyncio task alongside the main clock loop.
    Subscribes to command topics and publishes state periodically.
    """

    def __init__(self, config: MqttConfig, handler: CommandHandler) -> None:
        self._config = config
        self._handler = handler
        self._running = False
        self._client: Any = None

    @property
    def topic_command(self) -> str:
        """MQTT topic for receiving commands."""
        return f"{self._config.topic_prefix}/{self._config.device_id}/command"

    @property
    def topic_state(self) -> str:
        """MQTT topic for publishing state."""
        return f"{self._config.topic_prefix}/{self._config.device_id}/state"

    @property
    def topic_availability(self) -> str:
        """MQTT topic for availability (online/offline)."""
        return f"{self._config.topic_prefix}/{self._config.device_id}/availability"

    async def run(self) -> None:
        """Main MQTT loop — connect, subscribe, and process messages.

        Reconnects automatically on connection loss with exponential backoff.
        """
        try:
            import aiomqtt
        except ImportError:
            logger.error(
                "aiomqtt not installed. Install with: pip install aiomqtt\n"
                "MQTT remote control disabled."
            )
            return

        self._running = True
        retry_delay = 2.0

        while self._running:
            try:
                will = aiomqtt.Will(
                    topic=self.topic_availability,
                    payload="offline",
                    retain=True,
                )

                async with aiomqtt.Client(
                    hostname=self._config.host,
                    port=self._config.port,
                    username=self._config.username,
                    password=self._config.password,
                    will=will,
                ) as client:
                    self._client = client
                    retry_delay = 2.0  # Reset on successful connect

                    # Publish online status
                    await client.publish(self.topic_availability, "online", retain=True)

                    # Publish HA Discovery configs if enabled
                    if self._config.ha_discovery:
                        await self._publish_ha_discovery(client)

                    # Subscribe to command topic
                    await client.subscribe(self.topic_command)
                    logger.info(
                        f"MQTT connected to {self._config.host}:{self._config.port}, "
                        f"subscribed to {self.topic_command}"
                    )
                    print(
                        f"📡 MQTT connected ({self._config.host}:{self._config.port})"
                    )

                    # Publish initial state
                    await self._publish_state(client)

                    # Run message loop and periodic state publisher concurrently
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._message_loop(client))
                        tg.create_task(self._state_publisher(client))

            except asyncio.CancelledError:
                logger.info("MQTT task cancelled")
                self._client = None
                return
            except BaseException as e:
                self._client = None
                if not self._running or isinstance(e, KeyboardInterrupt):
                    return
                logger.warning(
                    f"MQTT connection lost: {e}. Retrying in {retry_delay:.0f}s..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 60.0)

    async def _message_loop(self, client: Any) -> None:
        """Process incoming MQTT messages."""
        async for message in client.messages:
            try:
                payload_str = message.payload.decode("utf-8")
                payload = json.loads(payload_str)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"MQTT: invalid message payload: {e}")
                continue

            command = self._handler.parse_command(payload)
            if command is None:
                continue

            result = await self._handler.execute(command)

            # Publish updated state after command execution
            await self._publish_state(client)

            if not result.success:
                logger.warning(f"MQTT command failed: {result.message}")

    async def _state_publisher(self, client: Any) -> None:
        """Periodically publish state to MQTT."""
        while self._running:
            await asyncio.sleep(self._config.state_interval)
            await self._publish_state(client)

    async def _publish_state(self, client: Any) -> None:
        """Publish current state to the state topic."""
        state = self._handler.get_state_payload()
        payload = json.dumps(state)
        try:
            await client.publish(self.topic_state, payload, retain=True)
        except Exception as e:
            logger.debug(f"Failed to publish state: {e}")

    async def _publish_ha_discovery(self, client: Any) -> None:
        """Publish Home Assistant MQTT Discovery configuration.

        Creates the following HA entities:
        - Switch: screen on/off
        - Select: force plugin
        - Text: display text
        - Sensor: active plugin (state)
        """
        device_id = self._config.device_id
        prefix = self._config.ha_discovery_prefix
        device_info = {
            "identifiers": [f"zeclock_{device_id}"],
            "name": f"zeClock ({device_id})",
            "manufacturer": "DMDTools",
            "model": "zeClock",
            "sw_version": "0.1.0",
        }
        availability = {
            "topic": self.topic_availability,
            "payload_available": "online",
            "payload_not_available": "offline",
        }

        # Switch: screen on/off
        switch_config = {
            "name": "Screen",
            "unique_id": f"zeclock_{device_id}_screen",
            "command_topic": self.topic_command,
            "state_topic": self.topic_state,
            "value_template": "{{ value_json.screen }}",
            "payload_on": json.dumps({"command": "screen_on"}),
            "payload_off": json.dumps({"command": "screen_off"}),
            "state_on": "on",
            "state_off": "off",
            "device": device_info,
            "availability": availability,
            "icon": "mdi:monitor",
        }
        await client.publish(
            f"{prefix}/switch/{device_id}/screen/config",
            json.dumps(switch_config),
            retain=True,
        )

        # Sensor: active plugin
        sensor_config = {
            "name": "Active Plugin",
            "unique_id": f"zeclock_{device_id}_active_plugin",
            "state_topic": self.topic_state,
            "value_template": "{{ value_json.active_plugin or 'none' }}",
            "device": device_info,
            "availability": availability,
            "icon": "mdi:puzzle",
        }
        await client.publish(
            f"{prefix}/sensor/{device_id}/active_plugin/config",
            json.dumps(sensor_config),
            retain=True,
        )

        # Sensor: display mode
        mode_config = {
            "name": "Display Mode",
            "unique_id": f"zeclock_{device_id}_display_mode",
            "state_topic": self.topic_state,
            "value_template": "{{ value_json.display_mode }}",
            "device": device_info,
            "availability": availability,
            "icon": "mdi:television",
        }
        await client.publish(
            f"{prefix}/sensor/{device_id}/display_mode/config",
            json.dumps(mode_config),
            retain=True,
        )

        logger.info("MQTT: Home Assistant Discovery configs published")

    def stop(self) -> None:
        """Signal the MQTT loop to stop."""
        self._running = False
