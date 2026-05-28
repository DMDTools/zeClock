"""PluginHelpers - Shared rendering utilities for plugin authors.

Provides access to the zeClock font system, frame creation,
and common drawing operations for DMD displays.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

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


class PluginHelpers:
    """Shared rendering utilities available to all plugins.

    Provides access to the zeClock font system, frame creation,
    and common drawing operations for DMD displays.
    """

    def __init__(self, width: int, height: int, resources_path: Path):
        """Initialize PluginHelpers.

        Args:
            width: Display width in pixels (e.g. 128 or 256).
            height: Display height in pixels (e.g. 32 or 64).
            resources_path: Path to the resources directory containing Fonts/.
        """
        self.width = width
        self.height = height
        self.resources_path = resources_path
        self._fonts: Dict[str, BitmapFont] = {}

    def _get_font(self, font_name: str) -> Optional[BitmapFont]:
        """Lazy-load and cache a BitmapFont by name.

        Args:
            font_name: Name of the .fnt file (without extension), e.g. "STANDARD".

        Returns:
            BitmapFont instance, or None if the font file doesn't exist.
        """
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
        font_name: str = "STANDARD",
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
            text_width = font.get_text_width(text)
            text_height = font.char_height

            buf_width = max(text_width, 1)
            buf_height = max(text_height, 1)
            text_img = font.render_text(text, buf_width, buf_height)
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

        Args:
            background: Base frame.
            foreground: Frame to overlay (black pixels are transparent).

        Returns:
            Composited frame.
        """
        bg_data = bytearray(background.tobytes())
        fg_data = foreground.tobytes()
        mode = background.mode

        if mode == "RGB":
            # 3 bytes per pixel
            for i in range(0, len(fg_data), 3):
                if fg_data[i] > 0 or fg_data[i + 1] > 0 or fg_data[i + 2] > 0:
                    bg_data[i] = fg_data[i]
                    bg_data[i + 1] = fg_data[i + 1]
                    bg_data[i + 2] = fg_data[i + 2]
        else:
            # Grayscale - 1 byte per pixel
            for i in range(len(fg_data)):
                if fg_data[i] > 0:
                    bg_data[i] = fg_data[i]

        return Image.frombytes(mode, background.size, bytes(bg_data))

    def get_font_names(self) -> List[str]:
        """List available .fnt font names in the resources directory.

        Returns:
            List of font names (without .fnt extension), e.g. ["STANDARD", "MENU", "SYSTEM"].
        """
        fonts_dir = self.resources_path / "Fonts"
        if not fonts_dir.exists():
            return []
        return sorted([f.stem for f in fonts_dir.glob("*.fnt")])

    def get_text_width(self, text: str, font_name: str = "STANDARD") -> int:
        """Calculate the pixel width of rendered text without actually rendering.

        Useful for layout calculations before calling render_text.

        Args:
            text: The text to measure.
            font_name: Name of the .fnt font file (without extension).

        Returns:
            Width in pixels, or 0 if font not found or text is empty.
        """
        font = self._get_font(font_name)
        if font is None or not text:
            return 0
        return font.get_text_width(text)

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
