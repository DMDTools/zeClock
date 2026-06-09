"""GifPlugin - Displays animated GIFs on the DMD.

Picks a random GIF from a configurable directory, plays it once
respecting each frame's native delay, then signals completion.

For pixel-perfect GIFs (exact integer multiples of the display size),
the configured upscale algorithm (epx, hq2x, nearest) is used.
For GIFs that need arbitrary rescaling, LANCZOS is used.

Frame extraction and upscaling run in a background thread so the
clock keeps rendering during loading.
"""

import asyncio
import logging
import random
import threading
from pathlib import Path
from typing import List, Optional

from PIL import Image

from .base import ClockPlugin, ConfigField, PluginNotConfiguredError
from ..overlay import upscale_nx

logger = logging.getLogger(__name__)

# Default GIF directory relative to user plugins path
from ..paths import get_plugins_dir  # noqa: E402

DEFAULT_GIF_DIR = get_plugins_dir() / "gif"


class GifPlugin(ClockPlugin):
    """Plays a random animated GIF from a directory on the DMD display."""

    def __init__(self) -> None:
        """Initialize with empty state."""
        self._helpers = None
        self._frames: List[Image.Image] = []
        self._frame_delays: List[int] = []
        self._frame_index: int = 0
        self._upscale_mode: str = "epx"
        # Background loading state
        self._load_thread: Optional[threading.Thread] = None
        self._frames_lock = threading.Lock()
        self._load_done = False

    @property
    def name(self) -> str:
        return "gif"

    @property
    def description(self) -> str:
        return "Displays animated GIFs on the DMD"

    @property
    def config_schema(self) -> List[ConfigField]:
        """Declare configuration fields for the gif plugin."""
        return [
            ConfigField(
                "gif_dir",
                "GIF Directory",
                "text",
                required=True,
                description="Path to directory containing .gif files",
            )
        ]

    @property
    def frame_delay_ms(self) -> int:
        # Return current frame's delay; default 100ms if unknown
        if self._frame_delays and self._frame_index < len(self._frame_delays):
            return self._frame_delays[self._frame_index]
        return 100

    async def initialize(self, config: dict) -> None:
        """Load a random GIF in background.

        Config keys:
            gif_dir (str): Path to directory containing .gif files.
                           Default: ~/.zeclock/plugins/gif/

        Raises:
            PluginNotConfiguredError: If gif_dir is missing, does not exist,
                or contains zero .gif files.
        """
        self._helpers = config.get("_helpers")
        self._upscale_mode = config.get("_upscale_mode", "epx")

        # Wait for any existing load thread to finish before resetting state
        if self._load_thread and self._load_thread.is_alive():
            self._load_thread.join(timeout=2.0)

        self._frames = []
        self._frame_delays = []
        self._frame_index = 0
        self._load_done = False

        # Resolve GIF directory
        gif_dir_str = config.get("gif_dir")
        if gif_dir_str:
            gif_dir = Path(gif_dir_str).expanduser()
        else:
            gif_dir = DEFAULT_GIF_DIR

        if not gif_dir.is_dir():
            raise PluginNotConfiguredError(
                f"Gif plugin: directory does not exist: {gif_dir}"
            )

        # Find all .gif files recursively
        gif_files = list(gif_dir.rglob("*.gif"))
        if not gif_files:
            raise PluginNotConfiguredError(
                f"Gif plugin: no .gif files found in {gif_dir}"
            )

        # Pick one at random
        gif_path = random.choice(gif_files)
        logger.info("[gif] Loading GIF: %s (in background)", gif_path.name)

        # Load in background thread
        self._load_thread = threading.Thread(
            target=self._load_gif_background,
            args=(gif_path,),
            daemon=True,
        )
        self._load_thread.start()

    def _load_gif_background(self, path: Path) -> None:
        """Extract all frames in a background thread.

        Frames are appended progressively so render_frame() can start
        serving them before all frames are ready.
        """
        width = self._helpers.width if self._helpers else 128
        height = self._helpers.height if self._helpers else 32

        try:
            gif = Image.open(path)
            gif_size = gif.size  # Original GIF dimensions

            frame_index = 0
            needs_resize = gif_size != (width, height)
            while True:
                try:
                    gif.seek(frame_index)
                except EOFError:
                    break

                # Convert frame to RGB
                frame = gif.convert("RGB")

                # Crop/upscale to display size if dimensions don't match
                if needs_resize:
                    frame = self._crop_to_fit(frame, width, height)

                # Get frame duration (in ms), default 100ms
                duration = gif.info.get("duration", 100)
                if duration < 20:
                    duration = 100

                # Make frame available immediately
                with self._frames_lock:
                    self._frames.append(frame)
                    self._frame_delays.append(duration)

                frame_index += 1

            gif.close()

            if needs_resize:
                # Determine if it was pixel-art upscale or LANCZOS
                src_w, src_h = gif_size
                scale_x = width / src_w if src_w > 0 else 0
                scale_y = height / src_h if src_h > 0 else 0
                if scale_x == scale_y and scale_x == int(scale_x) and scale_x >= 2:
                    algo = self._upscale_mode
                else:
                    algo = "lanczos"
                logger.info(
                    "[gif] Loaded %d frames (%dx%d → %dx%d, upscale=%s)",
                    frame_index,
                    src_w,
                    src_h,
                    width,
                    height,
                    algo,
                )
            else:
                logger.info(
                    "[gif] Loaded %d frames (%dx%d, upscale=none)",
                    frame_index,
                    width,
                    height,
                )

        except Exception as e:
            logger.warning("[gif] Failed to load GIF %s: %s", path.name, e)

        self._load_done = True

    def _crop_to_fit(
        self, frame: Image.Image, target_w: int, target_h: int
    ) -> Image.Image:
        """Resize and center-crop a frame to target dimensions.

        If the source is an exact integer multiple of the target (pixel-art
        upscale), uses the configured upscale algorithm.
        Otherwise falls back to LANCZOS for arbitrary rescaling.
        """
        src_w, src_h = frame.size

        # Check if this is a pixel-perfect integer scale relationship
        if src_w > 0 and src_h > 0:
            scale_x = target_w / src_w
            scale_y = target_h / src_h
            if scale_x == scale_y and scale_x == int(scale_x) and scale_x >= 2:
                scale = int(scale_x)
                if frame.mode == "RGB":
                    if self._upscale_mode == "nearest":
                        return frame.resize(
                            (target_w, target_h), Image.Resampling.NEAREST
                        )
                    else:
                        r, g, b = frame.split()
                        r2 = upscale_nx(r, scale, mode=self._upscale_mode)
                        g2 = upscale_nx(g, scale, mode=self._upscale_mode)
                        b2 = upscale_nx(b, scale, mode=self._upscale_mode)
                        return Image.merge("RGB", (r2, g2, b2))
                else:
                    return upscale_nx(frame, scale, mode=self._upscale_mode)

        # Arbitrary rescaling — LANCZOS for best quality
        fit_scale = max(target_w / src_w, target_h / src_h)
        new_w = int(src_w * fit_scale)
        new_h = int(src_h * fit_scale)

        frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        frame = frame.crop((left, top, left + target_w, top + target_h))

        return frame

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Return the next GIF frame, or None when done.

        Frames are served progressively as they become available from
        the background loading thread.
        """
        with self._frames_lock:
            available = len(self._frames)

        if self._frame_index >= available:
            if self._load_done:
                return None
            else:
                # Still loading — wait briefly
                await asyncio.sleep(0.01)
                with self._frames_lock:
                    available = len(self._frames)
                if self._frame_index >= available:
                    return None

        if self._frame_index == 0:
            logger.info("[gif] Start rendering")

        with self._frames_lock:
            frame = self._frames[self._frame_index]
        self._frame_index += 1
        return frame

    async def cleanup(self) -> None:
        """Release frame data."""
        if self._load_thread and self._load_thread.is_alive():
            self._load_thread.join(timeout=1.0)
        self._frames = []
        self._frame_delays = []
        self._frame_index = 0
        self._load_done = False
