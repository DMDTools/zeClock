"""PluginHelpers - Shared rendering utilities for plugin authors.

Provides access to the zeClock font system, frame creation,
and common drawing operations for DMD displays.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops

from ..colors import COLOR_MAP
from ..overlay import upscale_2x
from ..readers.fnt_reader import BitmapFont, load_font


def draw_staleness_indicator(
    frame: Image.Image,
    current_frame: int,
    frame_delay_ms: int,
) -> None:
    """Draw a blinking red dot in the top-right corner as a staleness indicator.

    The dot blinks at approximately 500ms intervals by toggling visibility
    based on the current frame count and frame_delay_ms. The dot is drawn
    as a 3x3 pixel block in red to be distinguishable from normal content.

    This is a standalone function usable without a PluginHelpers instance.

    Args:
        frame: The frame to draw the indicator onto (modified in place).
        current_frame: Total frame count for blink timing.
        frame_delay_ms: Delay between frames in ms (for blink calculation).
    """
    width, height = frame.size

    # Calculate blink interval in frames (~500ms toggle)
    blink_interval_frames = max(1, 500 // frame_delay_ms)

    # Determine if the dot should be visible this frame
    blink_cycle = current_frame // blink_interval_frames
    dot_visible = (blink_cycle % 2) == 0

    if not dot_visible:
        return

    # Draw a 3x3 red dot in the top-right corner (2px margin)
    dot_color = (255, 0, 0)
    dot_x = width - 5  # 2px margin from right edge
    dot_y = 2  # 2px margin from top edge
    pixels = frame.load()
    assert pixels is not None

    for dy in range(3):
        for dx in range(3):
            px = dot_x + dx
            py = dot_y + dy
            if 0 <= px < width and 0 <= py < height:
                pixels[px, py] = dot_color


# Default confetti color palettes
CONFETTI_COLORS_PARTY = [
    (255, 255, 0),
    (255, 100, 0),
    (0, 255, 100),
    (100, 100, 255),
    (255, 50, 200),
    (255, 255, 255),
]

CONFETTI_COLORS_WARM = [
    (255, 255, 0),
    (255, 200, 0),
    (255, 128, 0),
    (255, 80, 0),
    (255, 255, 255),
]

CONFETTI_COLORS_COOL = [
    (0, 200, 255),
    (100, 100, 255),
    (0, 255, 150),
    (200, 100, 255),
    (255, 255, 255),
]


class ConfettiAnimation:
    """Reusable confetti particle animation for DMD displays.

    Creates particles that shoot upward from the bottom of the screen
    (like confetti cannons) and fall back down with gravity. Supports
    different intensities and color palettes.

    Usage::

        # Create a celebration
        confetti = ConfettiAnimation(width=128, height=32)
        confetti.start(intensity="big")

        # Each frame:
        if confetti.is_active:
            confetti.update()
            confetti.draw(frame)

        # Check if animation is done:
        if confetti.is_finished:
            ...

    Intensities:
        - "small": 8 particles, 1s duration (point scored)
        - "medium": 20 particles, 2s duration
        - "big": 40 particles, 3.5s duration (match won)

    Args:
        width: Display width in pixels.
        height: Display height in pixels.
    """

    def __init__(self, width: int = 128, height: int = 32):
        self.width = width
        self.height = height
        self._particles: List[Dict] = []
        self._start_time: float = 0.0
        self._duration: float = 0.0
        self._active: bool = False

    @property
    def is_active(self) -> bool:
        """Whether the animation is currently playing."""
        return self._active

    @property
    def is_finished(self) -> bool:
        """Whether the animation has completed."""
        if not self._active:
            return True
        return (time.time() - self._start_time) >= self._duration

    def start(
        self,
        intensity: str = "big",
        colors: Optional[List[Tuple[int, int, int]]] = None,
        origin_x: Optional[float] = None,
    ) -> None:
        """Start a confetti animation.

        Args:
            intensity: "small" (8 particles, 1s), "medium" (20, 2s), or "big" (40, 3.5s).
            colors: Custom color palette. Defaults to CONFETTI_COLORS_PARTY.
            origin_x: X position for the cannon origin. None = cannons from both sides.
        """
        import random as _rnd

        palette = colors or CONFETTI_COLORS_PARTY
        self._particles = []
        self._start_time = time.time()
        self._active = True

        if intensity == "small":
            count = 8
            self._duration = 1.0
        elif intensity == "medium":
            count = 20
            self._duration = 2.0
        else:  # "big"
            count = 40
            self._duration = 3.5

        for _ in range(count):
            if origin_x is not None:
                x = origin_x + _rnd.uniform(-10, 10)
            else:
                # Two cannons: bottom-left and bottom-right
                side = _rnd.choice(["left", "right"])
                if side == "left":
                    x = _rnd.uniform(self.width * 0.1, self.width * 0.4)
                else:
                    x = _rnd.uniform(self.width * 0.6, self.width * 0.9)

            self._particles.append(
                {
                    "x": x,
                    "y": float(self.height),
                    "vx": _rnd.uniform(-1.5, 1.5),
                    "vy": _rnd.uniform(-3.5, -1.0),
                    "color": _rnd.choice(palette),
                    "size": _rnd.randint(1, 2 if intensity == "small" else 3),
                }
            )

    def stop(self) -> None:
        """Stop the animation immediately."""
        self._active = False
        self._particles = []

    def update(self) -> None:
        """Advance particle physics by one frame. Call once per render loop."""
        if not self._active:
            return

        if self.is_finished:
            self._active = False
            self._particles = []
            return

        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.06  # gravity
            # Wrap horizontally
            if p["x"] < 0:
                p["x"] = float(self.width)
            elif p["x"] > self.width:
                p["x"] = 0.0

    def draw(self, frame: Image.Image) -> None:
        """Draw confetti particles onto a frame.

        Args:
            frame: PIL Image to draw onto (modified in place).
        """
        if not self._active or not self._particles:
            return

        from PIL import ImageDraw

        draw = ImageDraw.Draw(frame)
        w, h = frame.size
        for p in self._particles:
            px = int(p["x"])
            py = int(p["y"])
            sz = p["size"]
            if 0 <= px < w and 0 <= py < h:
                draw.rectangle([px, py, px + sz - 1, py + sz - 1], fill=p["color"])


class PluginHelpers:
    """Shared rendering utilities available to all plugins.

    Provides access to the zeClock font system, frame creation,
    and common drawing operations for DMD displays.
    """

    def __init__(
        self,
        width: int,
        height: int,
        resources_path: Path,
        upscale_mode: str = "epx",
        default_font: str = "STANDARD",
    ):
        """Initialize PluginHelpers.

        Args:
            width: Display width in pixels (e.g. 128 or 256).
            height: Display height in pixels (e.g. 32 or 64).
            resources_path: Path to the resources directory containing Fonts/.
            upscale_mode: Upscaling algorithm for HD mode ("epx", "hq2x", or "nearest").
            default_font: Default font name used when no font_name is specified.
        """
        self.width = width
        self.height = height
        self.resources_path = resources_path
        self._fonts: Dict[str, BitmapFont] = {}
        # Font scale factor for HD displays (fonts are designed for 128x32)
        self._font_scale = max(1, min(width // 128, height // 32))
        self._upscale_mode = upscale_mode
        self.default_font = default_font

    def _resolve_font_name(self, font_name: Optional[str]) -> str:
        """Resolve font name, using default_font if None."""
        return font_name if font_name is not None else self.default_font

    def _get_font(self, font_name: str) -> Optional[BitmapFont]:
        """Lazy-load and cache a BitmapFont by name.

        In HD mode (scale > 1), automatically loads the _HD variant if available,
        which provides pixel-perfect 2x glyphs without runtime upscaling.

        Args:
            font_name: Name of the .fnt file (without extension), e.g. "STANDARD".

        Returns:
            BitmapFont instance, or None if the font file doesn't exist.
        """
        # In HD mode, try the _HD variant first
        if self._font_scale > 1:
            hd_name = f"{font_name}_HD"
            if hd_name not in self._fonts:
                hd_path = self.resources_path / "Fonts" / f"{hd_name}.fnt"
                if hd_path.exists():
                    try:
                        self._fonts[hd_name] = load_font(hd_path)
                    except Exception:
                        pass
            if hd_name in self._fonts:
                return self._fonts[hd_name]

        # Fall back to standard font
        if font_name not in self._fonts:
            font_path = self.resources_path / "Fonts" / f"{font_name}.fnt"
            if font_path.exists():
                try:
                    self._fonts[font_name] = load_font(font_path)
                except Exception:
                    return None
            else:
                return None
        return self._fonts[font_name]

    def create_frame(self, color: Tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
        """Create a blank RGB frame with the correct display dimensions.

        Args:
            color: Background fill color as (R, G, B) tuple. Default is black.

        Returns:
            PIL Image in RGB mode at (self.width, self.height).
        """
        return Image.new("RGB", (self.width, self.height), color)

    def render_text(
        self,
        text: str,
        x: int = 0,
        y: int = 0,
        color: Tuple[int, int, int] = (255, 128, 0),
        font_name: Optional[str] = None,
        centered: bool = False,
    ) -> Image.Image:
        """Render text using the DotClk bitmap font system.

        Args:
            text: The string to render.
            x: X position (ignored if centered=True).
            y: Y position for the text top.
            color: RGB color tuple for the text.
            font_name: Name of the .fnt font file (without extension).
            centered: If True, center text horizontally on the frame.

        Returns:
            PIL Image in RGB mode containing the rendered text on black background.
        """
        frame = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        font_name = self._resolve_font_name(font_name)
        font = self._get_font(font_name)
        if font is None or not text:
            return frame

        if centered:
            # Use the BitmapFont's render_text which returns a grayscale image
            # centered in the given dimensions, then colorize
            grayscale = font.render_text(text, self.width, self.height)
            gray_data = grayscale.tobytes()
            rgb_data = bytearray(self.width * self.height * 3)

            for i, pixel in enumerate(gray_data):
                if pixel > 0:
                    offset = i * 3
                    rgb_data[offset] = (color[0] * pixel) // 255
                    rgb_data[offset + 1] = (color[1] * pixel) // 255
                    rgb_data[offset + 2] = (color[2] * pixel) // 255

            frame = Image.frombytes("RGB", (self.width, self.height), bytes(rgb_data))
        else:
            # Render at a specific position
            font = self._get_font(font_name)
            if font is None or not text:
                return frame

            text_width = font.get_text_width(text)
            text_height = font.char_height

            buf_width = max(text_width, 1)
            buf_height = max(text_height, 1)
            # Render at native font size (HD fonts are already 2x)
            text_img = font._render_text_native(text, buf_width, buf_height)

            # Only upscale if using a standard (non-HD) font in HD mode
            scale = self._font_scale
            is_hd_font = font.name.endswith("_HD") if font.name else False
            if scale > 1 and not is_hd_font:
                buf_width *= scale
                buf_height *= scale
                if scale == 2 and self._upscale_mode in ("epx", "hq2x"):
                    text_img = upscale_2x(text_img, mode=self._upscale_mode)
                else:
                    # For scale != 2 or nearest mode, use PIL resize
                    text_img = text_img.resize(
                        (buf_width, buf_height), Image.Resampling.NEAREST
                    )

            text_data = text_img.tobytes()

            # Colorize and place at (x, y)
            rgb_data = bytearray(self.width * self.height * 3)
            for row in range(buf_height):
                for col in range(buf_width):
                    dest_x = x + col
                    dest_y = y + row
                    if 0 <= dest_x < self.width and 0 <= dest_y < self.height:
                        pixel_val = text_data[row * buf_width + col]
                        if pixel_val > 0:
                            offset = (dest_y * self.width + dest_x) * 3
                            rgb_data[offset] = (color[0] * pixel_val) // 255
                            rgb_data[offset + 1] = (color[1] * pixel_val) // 255
                            rgb_data[offset + 2] = (color[2] * pixel_val) // 255

            frame = Image.frombytes("RGB", (self.width, self.height), bytes(rgb_data))

        return frame

    def draw_icon(
        self,
        frame: Image.Image,
        icon_data: bytes,
        x: int,
        y: int,
        size: Tuple[int, int] = (16, 16),
        color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Image.Image:
        """Draw a pixel-art icon onto an existing frame.

        Args:
            frame: The target frame to draw onto (modified in place and returned).
            icon_data: Raw bitmap bytes (1 bit per pixel, row-major, MSB first).
            x: X position for top-left corner of the icon.
            y: Y position for top-left corner of the icon.
            size: (width, height) of the icon in pixels.
            color: RGB color to apply to set pixels.

        Returns:
            The modified frame with the icon drawn.
        """
        icon_width, icon_height = size
        pixels = frame.load()
        assert pixels is not None

        for row in range(icon_height):
            for col in range(icon_width):
                bit_index = row * icon_width + col
                byte_index = bit_index // 8
                bit_offset = 7 - (bit_index % 8)  # MSB first

                if byte_index < len(icon_data):
                    if (icon_data[byte_index] >> bit_offset) & 1:
                        dest_x = x + col
                        dest_y = y + row
                        if 0 <= dest_x < frame.width and 0 <= dest_y < frame.height:
                            pixels[dest_x, dest_y] = color

        return frame

    def composite_frames(
        self,
        background: Image.Image,
        foreground: Image.Image,
    ) -> Image.Image:
        """Composite foreground onto background using OR blending (DotBlt style).

        Non-black pixels in the foreground overwrite the background.
        Uses PIL's C-native operations for performance.

        Args:
            background: Base frame.
            foreground: Frame to overlay (black pixels are transparent).

        Returns:
            Composited frame.
        """
        # Create a binary mask where foreground is non-black
        if foreground.mode == "RGB":
            # Max of channels — any non-zero channel means non-black
            r, g, b = foreground.split()
            combined = ImageChops.lighter(ImageChops.lighter(r, g), b)
            # Threshold to binary: any value > 0 becomes 255
            mask = combined.point(lambda p: 255 if p > 0 else 0)
        else:
            mask = foreground.point(lambda p: 255 if p > 0 else 0)

        return Image.composite(foreground, background, mask)

    def get_font_names(self) -> List[str]:
        """List available .fnt font names in the resources directory.

        Returns:
            List of font names (without .fnt extension), e.g. ["STANDARD", "MENU", "SYSTEM"].
        """
        fonts_dir = self.resources_path / "Fonts"
        if not fonts_dir.exists():
            return []
        return sorted([f.stem for f in fonts_dir.glob("*.fnt")])

    def get_text_width(self, text: str, font_name: Optional[str] = None) -> int:
        """Calculate the pixel width of rendered text without actually rendering.

        Returns the native width from the font (HD fonts already have 2x widths).

        Args:
            text: The text to measure.
            font_name: Name of the .fnt font file (without extension).

        Returns:
            Width in pixels, or 0 if font not found or text is empty.
        """
        font_name = self._resolve_font_name(font_name)
        font = self._get_font(font_name)
        if font is None or not text:
            return 0
        native_width = font.get_text_width(text)
        # If using a standard font in HD mode, width needs scaling
        is_hd_font = font.name.endswith("_HD") if font.name else False
        if self._font_scale > 1 and not is_hd_font:
            return native_width * self._font_scale
        return native_width

    def draw_staleness_indicator(
        self,
        frame: Image.Image,
        current_frame: int,
        frame_delay_ms: int,
    ) -> None:
        """Draw a blinking red dot in the top-right corner as a staleness indicator.

        Delegates to the module-level draw_staleness_indicator function.

        Args:
            frame: The frame to draw the indicator onto (modified in place).
            current_frame: Total frame count for blink timing.
            frame_delay_ms: Delay between frames in ms (for blink calculation).
        """
        draw_staleness_indicator(frame, current_frame, frame_delay_ms)

    def resolve_color(
        self, color_name: str, default: str = "orange"
    ) -> Tuple[int, int, int]:
        """Resolve a color name to an RGB tuple using the shared palette.

        Args:
            color_name: Color name (e.g. "orange", "blue", "red").
            default: Fallback color name if color_name is not found.

        Returns:
            RGB tuple for the resolved color.
        """
        return COLOR_MAP.get(color_name, COLOR_MAP.get(default, (255, 128, 0)))

    def render_text_right_aligned(
        self,
        text: str,
        y: int,
        margin: int = 1,
        color: Tuple[int, int, int] = (255, 128, 0),
        font_name: Optional[str] = None,
    ) -> Image.Image:
        """Render text right-aligned on the frame.

        Args:
            text: The string to render.
            y: Y position for the text top.
            margin: Right margin in pixels (default: 1).
            color: RGB color tuple for the text.
            font_name: Name of the .fnt font file (without extension).

        Returns:
            PIL Image in RGB mode containing the rendered text.
        """
        text_width = self.get_text_width(text, font_name)
        x = self.width - text_width - margin
        return self.render_text(text, x=x, y=y, color=color, font_name=font_name)

    def render_text_centered_at(
        self,
        text: str,
        cx: int,
        y: int,
        color: Tuple[int, int, int] = (255, 128, 0),
        font_name: Optional[str] = None,
    ) -> Image.Image:
        """Render text centered horizontally around a given x coordinate.

        Args:
            text: The string to render.
            cx: Center x coordinate.
            y: Y position for the text top.
            color: RGB color tuple for the text.
            font_name: Name of the .fnt font file (without extension).

        Returns:
            PIL Image in RGB mode containing the rendered text.
        """
        text_width = self.get_text_width(text, font_name)
        x = cx - text_width // 2
        return self.render_text(text, x=x, y=y, color=color, font_name=font_name)
