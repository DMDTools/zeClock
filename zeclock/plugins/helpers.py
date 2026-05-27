"""PluginHelpers - Shared rendering utilities for plugin authors.

Provides access to the zeClock font system, frame creation,
and common drawing operations for DMD displays.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from ..readers.fnt_reader import BitmapFont, load_font


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

    def create_frame(
        self, color: Tuple[int, int, int] = (0, 0, 0)
    ) -> Image.Image:
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

        # Use the BitmapFont's render_text which returns a grayscale image
        # centered in the given dimensions
        grayscale = font.render_text(text, self.width, self.height)

        # Convert grayscale to RGB with the specified color
        gray_array = np.asarray(grayscale)

        if centered:
            # The BitmapFont.render_text already centers the text,
            # so we just colorize it directly
            rgb_array = np.zeros(
                (self.height, self.width, 3), dtype=np.uint8
            )
            intensity = gray_array / 255.0
            for i in range(3):
                rgb_array[:, :, i] = (color[i] * intensity).astype(np.uint8)
            frame = Image.fromarray(rgb_array, "RGB")
        else:
            # Render at a specific position: render text into a temporary
            # buffer then place it at (x, y)
            text_width = font.get_text_width(text)
            text_height = font.char_height

            # Render text into a buffer sized to fit
            buf_width = max(text_width, 1)
            buf_height = max(text_height, 1)
            text_img = font.render_text(text, buf_width, buf_height)
            text_array = np.asarray(text_img)

            # Colorize and place at (x, y)
            rgb_array = np.zeros(
                (self.height, self.width, 3), dtype=np.uint8
            )
            for row in range(buf_height):
                for col in range(buf_width):
                    dest_x = x + col
                    dest_y = y + row
                    if 0 <= dest_x < self.width and 0 <= dest_y < self.height:
                        pixel_val = text_array[row, col]
                        if pixel_val > 0:
                            intensity = pixel_val / 255.0
                            for i in range(3):
                                rgb_array[dest_y, dest_x, i] = int(
                                    color[i] * intensity
                                )
            frame = Image.fromarray(rgb_array, "RGB")

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

        for row in range(icon_height):
            for col in range(icon_width):
                bit_index = row * icon_width + col
                byte_index = bit_index // 8
                bit_offset = 7 - (bit_index % 8)  # MSB first

                if byte_index < len(icon_data):
                    if (icon_data[byte_index] >> bit_offset) & 1:
                        dest_x = x + col
                        dest_y = y + row
                        if (
                            0 <= dest_x < frame.width
                            and 0 <= dest_y < frame.height
                        ):
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
        bg_array = np.asarray(background).copy()
        fg_array = np.asarray(foreground)

        # Create mask where foreground is non-black (any channel > 0)
        if fg_array.ndim == 3:
            fg_mask = np.any(fg_array > 0, axis=2)
            # Where foreground is non-black, use foreground pixels
            bg_array[fg_mask] = fg_array[fg_mask]
        elif fg_array.ndim == 2:
            fg_mask = fg_array > 0
            bg_array[fg_mask] = fg_array[fg_mask]

        return Image.fromarray(bg_array, background.mode)

    def get_font_names(self) -> List[str]:
        """List available .fnt font names in the resources directory.

        Returns:
            List of font names (without .fnt extension), e.g. ["STANDARD", "MENU", "SYSTEM"].
        """
        fonts_dir = self.resources_path / "Fonts"
        if not fonts_dir.exists():
            return []
        return sorted(
            [f.stem for f in fonts_dir.glob("*.fnt")]
        )

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
