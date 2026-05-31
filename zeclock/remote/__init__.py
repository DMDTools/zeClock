"""Remote control module for zeClock.

Provides MQTT and REST API interfaces for controlling the clock remotely.
Both protocols share a common CommandHandler that executes commands against
the ZeClock instance.
"""

from .command_handler import CommandHandler, RemoteCommand
from .mqtt_remote import MqttRemote
from .rest_remote import RestRemote

__all__ = ["CommandHandler", "RemoteCommand", "MqttRemote", "RestRemote"]
