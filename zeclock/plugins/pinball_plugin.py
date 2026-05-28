"""PinballPlugin - Built-in plugin wrapping existing .scn animation playback.

This plugin implements the ClockPlugin interface and wraps the existing
pinball animation logic including DotBlt overlay composition and scene
storyboard metadata (frame_delay_ms, first_frame_delay, last_frame_delay,
clock_style, custom_x, custom_y, frame_layer).
"""

import logging
import random
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from PIL import Image

from .base import ClockPlugin
from ..overlay import overlay_or_rgb
from ..readers import BitmapFont, Scene, load_font, load_scene

logger = logging.getLogger(__name__)

# Default color mapping (same as clock.py)
COLOR_MAP = {
    "orange": (255, 128, 0),
    "blue": (0, 128, 255),
    "red": (255, 0, 0),
    "purple": (255, 0, 255),
    "green": (0, 255, 128),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "pink": (255, 64, 128),
}

DEFAULT_FRAME_DELAY_MS = 40
DEFAULT_COLOR = "orange"


class PinballPlugin(ClockPlugin):
    """Built-in plugin that plays .scn pinball animations with clock overlay.

    Wraps the existing animation playback logic from clock.py, randomly
    selecting a scene file and pre-computing all frames with DotBlt
    overlay composition during initialization.
    """

    @property
    def name(self) -> str:
        return "pinball"

    @property
    def description(self) -> str:
        return "Retro pinball DMD animations with clock overlay"

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms

    def __init__(self):
        """Initialize PinballPlugin with default state."""
        self._frame_delay_ms: int = DEFAULT_FRAME_DELAY_MS
        self._frames: List[Image.Image] = []
        self._frame_index: int = 0
        self._color: Tuple[int, int, int] = COLOR_MAP[DEFAULT_COLOR]
        self._animation_color: Tuple[int, int, int] = COLOR_MAP[DEFAULT_COLOR]
        self._animations_dir: Path = (
            Path.home() / ".zeclock" / "resources" / "animations"
        )
        self._font: Optional[BitmapFont] = None

    async def initialize(self, config: dict) -> None:
        """Initialize the plugin: select a scene and pre-compute frames.

        Config keys:
            color (str): Clock color name (default: "orange")
            animation_color (str): Animation color name (default: same as color)
            animations_dir (str|Path): Override animations directory path
            width (int): Display width (default: 128)
            height (int): Display height (default: 32)

        Args:
            config: Plugin-specific settings from plugins.yaml.
        """
        # Parse color settings
        color_name = config.get("color", DEFAULT_COLOR)
        self._color = COLOR_MAP.get(color_name, COLOR_MAP[DEFAULT_COLOR])

        animation_color_name = config.get("animation_color", color_name)
        self._animation_color = COLOR_MAP.get(animation_color_name, self._color)

        # Allow overriding animations directory (useful for testing)
        animations_dir = config.get("animations_dir")
        if animations_dir:
            self._animations_dir = Path(animations_dir)

        # Get display dimensions
        width = config.get("width", 128)
        height = config.get("height", 32)

        # Load font
        font_path = Path.home() / ".zeclock" / "resources" / "Fonts" / "STANDARD.fnt"
        font_path_override = config.get("font_path")
        if font_path_override:
            font_path = Path(font_path_override)

        if font_path.exists():
            try:
                self._font = load_font(font_path)
            except Exception as e:
                logger.warning("[pinball] Failed to load font %s: %s", font_path, e)

        # Find scene files
        scene_files = self._find_scene_files()
        if not scene_files:
            logger.warning(
                "[pinball] No .scn files found in %s - signaling completion immediately",
                self._animations_dir,
            )
            self._frames = []
            return

        # Randomly select a scene
        scene_path = random.choice(scene_files)
        logger.info("[pinball] Loading scene: %s", scene_path.name)

        try:
            scene = load_scene(scene_path, width, height)
        except Exception as e:
            logger.warning("[pinball] Failed to load scene %s: %s", scene_path.name, e)
            self._frames = []
            return

        # Set frame delay from scene metadata
        self._frame_delay_ms = (
            scene.frame_delay_ms if scene.frame_delay_ms > 0 else DEFAULT_FRAME_DELAY_MS
        )

        # Pre-compute frames
        self._frames = self._precompute_frames(scene, width, height)
        self._frame_index = 0

        logger.info(
            "[pinball] Animation ready: %s (%d frames, %.1f FPS)",
            scene_path.name,
            len(self._frames),
            1000.0 / self._frame_delay_ms,
        )

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Return the next pre-computed frame, or None when done.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if self._frame_index >= len(self._frames):
            return None

        if self._frame_index == 0:
            logger.info("[pinball] Start rendering")

        frame = self._frames[self._frame_index]
        self._frame_index += 1
        return frame

    async def cleanup(self) -> None:
        """Release resources."""
        self._frames = []
        self._frame_index = 0

    def _find_scene_files(self) -> List[Path]:
        """Find all .scn files in the animations directory.

        Returns:
            List of Path objects for found .scn files.
        """
        if not self._animations_dir.exists():
            return []
        return list(self._animations_dir.glob("**/*.scn"))

    def _precompute_frames(
        self, scene: Scene, width: int, height: int
    ) -> List[Image.Image]:
        """Pre-compute all animation frames with clock overlay.

        Applies DotBlt overlay composition respecting the scene's storyboard
        metadata (clock_style, custom_x, custom_y, frame_layer).

        Args:
            scene: The loaded Scene object.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            List of pre-computed RGB PIL Images.
        """
        frames: List[Image.Image] = []
        display_time = time.strftime("%H:%M")
        frame_delay = (
            scene.frame_delay_ms if scene.frame_delay_ms > 0 else DEFAULT_FRAME_DELAY_MS
        )

        for animation_frame in scene.frames:
            merged = self._create_merged_frame(
                animation_frame, display_time, scene, width, height
            )
            frames.append(merged)

        # Add first frame delay (repeat first frame)
        if scene.first_frame_delay > 0 and frames:
            first_frame_count = int(scene.first_frame_delay / frame_delay)
            frames = [frames[0]] * first_frame_count + frames

        # Add last frame delay (repeat last frame)
        if scene.last_frame_delay > 0 and frames:
            last_frame_count = int(scene.last_frame_delay / frame_delay)
            frames = frames + [frames[-1]] * last_frame_count

        return frames

    def _create_merged_frame(
        self,
        animation_frame: Image.Image,
        display_time: str,
        scene: Scene,
        width: int,
        height: int,
    ) -> Image.Image:
        """Create a single merged frame combining animation and clock overlay.

        Respects the scene's clock_style, custom_x, custom_y, and frame_layer
        settings for positioning and layer order.

        Args:
            animation_frame: The grayscale animation frame.
            display_time: The time string to render (e.g. "12:34").
            scene: The Scene object with storyboard metadata.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            Merged RGB PIL Image.
        """
        if self._font is None:
            # No font available - just colorize the animation frame
            from ..overlay import _colorize_grayscale

            return _colorize_grayscale(animation_frame, self._animation_color)

        # Render clock overlay based on clock_style
        if scene.clock_style == 1:
            # Custom position clock
            clock_frame = self._render_custom_clock(display_time, scene, width, height)
        else:
            # Standard centered clock
            clock_frame = self._font.render_text(display_time, width, height)

        # Apply DotBlt overlay with dual colors based on frame_layer
        if scene.frame_layer == 1:
            # Clock above animation: animation is base, clock is overlay
            merged = overlay_or_rgb(
                animation_frame, clock_frame, self._animation_color, self._color
            )
        else:
            # Clock behind animation (default): clock is base, animation is overlay
            merged = overlay_or_rgb(
                clock_frame, animation_frame, self._color, self._animation_color
            )

        return merged

    def _render_custom_clock(
        self,
        display_time: str,
        scene: Scene,
        width: int,
        height: int,
    ) -> Image.Image:
        """Render clock text at custom position specified by scene storyboard.

        Args:
            display_time: The time string to render.
            scene: The Scene with custom_x, custom_y coordinates.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            Grayscale PIL Image with clock text at custom position.
        """
        assert self._font is not None
        text_width = self._font.get_text_width(display_time)
        text_height = self._font.char_height

        # Calculate position (custom_x/y are center points)
        x_pos = max(0, min(scene.custom_x - (text_width // 2), width - text_width))
        y_pos = max(0, min(scene.custom_y - (text_height // 2), height - text_height))

        # Create clock frame at custom position
        clock_frame = Image.new("L", (width, height), 0)
        text_img = self._font.render_text(display_time, text_width, text_height)
        clock_frame.paste(text_img, (x_pos, y_pos))

        # Reposition mask to full canvas
        text_img_any: Any = text_img
        if hasattr(text_img, "mask_data") and text_img_any.mask_data:
            mask_width_bytes = (width // 8) + (1 if width % 8 else 0)
            full_mask = bytearray(height * mask_width_bytes)

            text_mask_width_bytes = (text_width // 8) + (1 if text_width % 8 else 0)

            for ty in range(text_height):
                for tx in range(text_width):
                    # Read bit from text mask
                    src_byte_idx = (tx // 8) + (ty * text_mask_width_bytes)
                    src_bit_pos = tx % 8
                    if src_byte_idx < len(text_img_any.mask_data):
                        mask_bit = (
                            text_img_any.mask_data[src_byte_idx] >> src_bit_pos
                        ) & 1
                        if mask_bit:
                            # Write bit to full mask
                            dest_x = x_pos + tx
                            dest_y = y_pos + ty
                            if 0 <= dest_x < width and 0 <= dest_y < height:
                                dest_byte_idx = (dest_x // 8) + (
                                    dest_y * mask_width_bytes
                                )
                                dest_bit_pos = dest_x % 8
                                full_mask[dest_byte_idx] |= 1 << dest_bit_pos

            clock_frame_any: Any = clock_frame
            clock_frame_any.mask_data = bytes(full_mask)
            clock_frame_any.mask_width_bytes = mask_width_bytes

        return clock_frame
