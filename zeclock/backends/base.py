"""Abstract base class for DMD display backends."""

from abc import ABC, abstractmethod
from typing import Tuple

from PIL import Image


class DMDBackend(ABC):
    """Abstract base class for DMD display backends."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the backend is currently connected to a display."""
        ...

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the display. Returns True on success."""
        ...

    @abstractmethod
    def send_frame(
        self,
        image: Image.Image,
        buffered: bool = True,
        color: Tuple[int, int, int] = (255, 128, 0),
    ) -> bool:
        """Send a frame to the display. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection to the display."""
        ...

    def __enter__(self) -> "DMDBackend":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()
