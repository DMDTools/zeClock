"""GifPlugin - Displays animated GIFs on the DMD.

Picks a random GIF from a configurable directory, plays it once
respecting each frame's native delay, then signals completion.
"""

import logging
import random
from pathlib import Path
from typing import List, Optional

from PIL import Image

from .base import ClockPlugin

logger = logging.getLogger(__name__)

# Default GIF directory relative to user plugins path
DEFAULT_GIF_DIR = Path.home() / ".zeclock" / "plugins" / "gif"


class GifPlugin(ClockPlugin):
    """Plays a random animated GIF from a directory on the DMD display."""

    def __init__(self) -> None:
        """Initialize with empty state."""
        self._helpers = None
        self._frames: List[Image.Image] = []
        self._frame_delays: List[int] = []
        self._frame_index: int = 0

    @property
    def name(self) -> str:
        return "gif"

    @property
    def description(self) -> str:
        return "Displays animated GIFs on the DMD"

    @property
    def frame_delay_ms(self) -> int:
        # Return current frame's delay; default 100ms if unknown
        if self._frame_delays and self._frame_index < len(self._frame_delays):
            return self._frame_delays[self._frame_index]
        return 100

    async def initialize(self, config: dict) -> None:
        """Load a random GIF and pre-extract all frames.

        Config keys:
            gif_dir (str): Path to directory containing .gif files.
                           Default: ~/.zeclock/plugins/gif/
        """
        self._helpers = config.get("_helpers")
        self._frames = []
        self._frame_delays = []
        self._frame_index = 0

        # Resolve GIF directory
        gif_dir_str = config.get("gif_dir")
        if gif_dir_str:
            gif_dir = Path(gif_dir_str).expanduser()
        else:
            gif_dir = DEFAULT_GIF_DIR

        if not gif_dir.exists():
            logger.warning("[gif] GIF directory does not exist: %s", gif_dir)
            return

        # Find all .gif files recursively
        gif_files = list(gif_dir.rglob("*.gif"))
        if not gif_files:
            logger.warning("[gif] No .gif files found in %s", gif_dir)
            return

        # Pick one at random
        gif_path = random.choice(gif_files)
        logger.info("[gif] Loading GIF: %s", gif_path.name)

        try:
            self._load_gif(gif_path)
        except Exception as e:
            logger.warning("[gif] Failed to load GIF %s: %s", gif_path.name, e)
            self._frames = []

    def _load_gif(self, path: Path) -> None:
        """Extract all frames and their delays from a GIF file.

        Frames are center-cropped to display dimensions if needed.

        Args:
            path: Path to the .gif file.
        """
        width = self._helpers.width if self._helpers else 128
        height = self._helpers.height if self._helpers else 32

        gif = Image.open(path)

        frame_index = 0
        while True:
            try:
                gif.seek(frame_index)
            except EOFError:
                break

            # Convert frame to RGB
            frame = gif.convert("RGB")

            # Crop to display size if dimensions don't match
            if frame.size != (width, height):
                frame = self._crop_to_fit(frame, width, height)

            self._frames.append(frame)

            # Get frame duration (in ms), default 100ms
            duration = gif.info.get("duration", 100)
            # Some GIFs have 0 duration meaning "as fast as possible"
            if duration < 20:
                duration = 100
            self._frame_delays.append(duration)

            frame_index += 1

        gif.close()
        logger.info("[gif] Loaded %d frames from GIF", len(self._frames))

    def _crop_to_fit(
        self, frame: Image.Image, target_w: int, target_h: int
    ) -> Image.Image:
        """Resize and center-crop a frame to target dimensions.

        Scales the image so it covers the target area, then crops
        from the center.

        Args:
            frame: Source PIL Image.
            target_w: Target width in pixels.
            target_h: Target height in pixels.

        Returns:
            Cropped PIL Image at (target_w, target_h).
        """
        src_w, src_h = frame.size

        # Scale to cover the target area
        scale = max(target_w / src_w, target_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)

        frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        frame = frame.crop((left, top, left + target_w, top + target_h))

        return frame

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Return the next GIF frame, or None when done.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if not self._frames or self._frame_index >= len(self._frames):
            return None

        if self._frame_index == 0:
            logger.info("[gif] Start rendering")

        frame = self._frames[self._frame_index]
        self._frame_index += 1
        return frame

    async def cleanup(self) -> None:
        """Release frame data."""
        self._frames = []
        self._frame_delays = []
        self._frame_index = 0
