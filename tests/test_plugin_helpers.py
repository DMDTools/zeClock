"""Tests for PluginHelpers module.

Validates Properties 17 and 18 from the design document:
- Property 17: PluginHelpers Frame Dimensions
- Property 18: PluginHelpers Text Width Consistency
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PIL import Image

from zeclock.plugins.helpers import PluginHelpers

# DotClk fonts are not available in CI (local submodule only)
DOTCLK_PATH = Path(__file__).parent.parent / "DotClk"
HAS_DOTCLK_FONTS = (DOTCLK_PATH / "Fonts").is_dir() and any(
    (DOTCLK_PATH / "Fonts").glob("*.fnt")
)
requires_fonts = pytest.mark.skipif(
    not HAS_DOTCLK_FONTS,
    reason="DotClk fonts not available (local resource, not in CI)",
)


def _frame_has_content(frame: Image.Image) -> bool:
    """Check if a frame has any non-black pixels."""
    return frame.getbbox() is not None


def _frame_is_black(frame: Image.Image) -> bool:
    """Check if a frame is entirely black."""
    return frame.getbbox() is None


def _rightmost_content_column(frame: Image.Image) -> int:
    """Find the rightmost column (x) that has non-black pixels. Returns -1 if empty."""
    bbox = frame.getbbox()
    if bbox is None:
        return -1
    # bbox is (left, upper, right, lower) — right is exclusive
    return bbox[2] - 1


@pytest.fixture
def resources_path():
    """Path to the DotClk fonts directory used as resources."""
    # Use the DotClk/Fonts directory which has .fnt files
    return Path(__file__).parent.parent / "DotClk"


@pytest.fixture
def helpers(resources_path):
    """Create a PluginHelpers instance with standard display dimensions."""
    return PluginHelpers(width=128, height=32, resources_path=resources_path)


@pytest.fixture
def helpers_large(resources_path):
    """Create a PluginHelpers instance with large display dimensions."""
    return PluginHelpers(width=256, height=64, resources_path=resources_path)


# --- Property-Based Tests: Property 17 - PluginHelpers Frame Dimensions ---
# Feature: plugin-system, Property 17: PluginHelpers Frame Dimensions
# **Validates: Requirements 2.5**


# Strategy for realistic display dimensions
# DMD displays are typically small; we test a range of plausible sizes
display_width_st = st.integers(min_value=1, max_value=512)
display_height_st = st.integers(min_value=1, max_value=128)

# Strategy for RGB color tuples
rgb_color_st = st.tuples(
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
)

# Strategy for text that the STANDARD font can render (digits, colon, slash, space, A, M, P)
renderable_text_st = st.text(
    alphabet="0123456789:/ AMP",
    min_size=1,
    max_size=20,
)


@given(width=display_width_st, height=display_height_st, color=rgb_color_st)
@settings(max_examples=200)
def test_property17_create_frame_dimensions_and_mode(width, height, color):
    """For any (width, height), create_frame() returns an RGB image at exactly (width, height).

    **Validates: Requirements 2.5**
    """
    resources_path = Path(__file__).parent.parent / "DotClk"
    helpers = PluginHelpers(width=width, height=height, resources_path=resources_path)
    frame = helpers.create_frame(color=color)

    assert isinstance(frame, Image.Image)
    assert frame.mode == "RGB"
    assert frame.size == (width, height)


@given(width=display_width_st, height=display_height_st, text=renderable_text_st)
@settings(max_examples=200)
def test_property17_render_text_dimensions_and_mode(width, height, text):
    """For any (width, height) and text, render_text() returns an RGB image at exactly (width, height).

    **Validates: Requirements 2.5**
    """
    resources_path = Path(__file__).parent.parent / "DotClk"
    helpers = PluginHelpers(width=width, height=height, resources_path=resources_path)
    frame = helpers.render_text(text)

    assert isinstance(frame, Image.Image)
    assert frame.mode == "RGB"
    assert frame.size == (width, height)


@given(
    width=display_width_st,
    height=display_height_st,
    text=renderable_text_st,
    color=rgb_color_st,
)
@settings(max_examples=200)
def test_property17_render_text_centered_dimensions(width, height, text, color):
    """For any (width, height), render_text() with centered=True returns RGB at (width, height).

    **Validates: Requirements 2.5**
    """
    resources_path = Path(__file__).parent.parent / "DotClk"
    helpers = PluginHelpers(width=width, height=height, resources_path=resources_path)
    frame = helpers.render_text(text, color=color, centered=True)

    assert isinstance(frame, Image.Image)
    assert frame.mode == "RGB"
    assert frame.size == (width, height)


@given(
    width=display_width_st,
    height=display_height_st,
    x=st.integers(min_value=0, max_value=200),
    y=st.integers(min_value=0, max_value=100),
    text=renderable_text_st,
)
@settings(max_examples=200)
def test_property17_render_text_positioned_dimensions(width, height, x, y, text):
    """For any (width, height) and position, render_text() returns RGB at (width, height).

    **Validates: Requirements 2.5**
    """
    resources_path = Path(__file__).parent.parent / "DotClk"
    helpers = PluginHelpers(width=width, height=height, resources_path=resources_path)
    frame = helpers.render_text(text, x=x, y=y)

    assert isinstance(frame, Image.Image)
    assert frame.mode == "RGB"
    assert frame.size == (width, height)


# --- Example-Based Tests for Property 17: Various Display Sizes ---


class TestFrameDimensionsExamples:
    """Example-based tests for specific display sizes (128x32, 256x64).

    **Validates: Requirements 2.5**
    """

    @pytest.mark.parametrize(
        "width,height",
        [
            (128, 32),
            (256, 64),
            (64, 16),
            (192, 48),
        ],
    )
    def test_create_frame_various_sizes(self, width, height, resources_path):
        helpers = PluginHelpers(
            width=width, height=height, resources_path=resources_path
        )
        frame = helpers.create_frame()
        assert frame.mode == "RGB"
        assert frame.size == (width, height)

    @pytest.mark.parametrize(
        "width,height",
        [
            (128, 32),
            (256, 64),
            (64, 16),
            (192, 48),
        ],
    )
    def test_render_text_various_sizes(self, width, height, resources_path):
        helpers = PluginHelpers(
            width=width, height=height, resources_path=resources_path
        )
        frame = helpers.render_text("12:00")
        assert frame.mode == "RGB"
        assert frame.size == (width, height)

    @pytest.mark.parametrize(
        "width,height",
        [
            (128, 32),
            (256, 64),
        ],
    )
    def test_render_text_centered_various_sizes(self, width, height, resources_path):
        helpers = PluginHelpers(
            width=width, height=height, resources_path=resources_path
        )
        frame = helpers.render_text("12:00", centered=True)
        assert frame.mode == "RGB"
        assert frame.size == (width, height)


class TestCreateFrame:
    """Tests for create_frame()."""

    def test_returns_rgb_image(self, helpers):
        frame = helpers.create_frame()
        assert frame.mode == "RGB"

    def test_correct_dimensions(self, helpers):
        frame = helpers.create_frame()
        assert frame.size == (128, 32)

    def test_correct_dimensions_large(self, helpers_large):
        frame = helpers_large.create_frame()
        assert frame.size == (256, 64)

    def test_default_black_background(self, helpers):
        frame = helpers.create_frame()
        # Check a pixel is black
        assert frame.getpixel((0, 0)) == (0, 0, 0)
        assert frame.getpixel((64, 16)) == (0, 0, 0)

    def test_custom_background_color(self, helpers):
        frame = helpers.create_frame(color=(255, 0, 0))
        assert frame.getpixel((0, 0)) == (255, 0, 0)
        assert frame.getpixel((64, 16)) == (255, 0, 0)


class TestRenderText:
    """Tests for render_text()."""

    def test_returns_rgb_image(self, helpers):
        frame = helpers.render_text("Hello")
        assert frame.mode == "RGB"

    def test_correct_dimensions(self, helpers):
        frame = helpers.render_text("Hello")
        assert frame.size == (128, 32)

    def test_correct_dimensions_large(self, helpers_large):
        frame = helpers_large.render_text("Hello")
        assert frame.size == (256, 64)

    def test_empty_text_returns_black_frame(self, helpers):
        frame = helpers.render_text("")
        assert _frame_is_black(frame)

    @requires_fonts
    def test_centered_text_has_content(self, helpers):
        frame = helpers.render_text("12:00", centered=True)
        assert _frame_has_content(frame)

    @requires_fonts
    def test_positioned_text_has_content(self, helpers):
        # STANDARD font only has digits, ':', '/', 'A', 'M', 'P', ' '
        frame = helpers.render_text("12:00", x=10, y=5)
        assert _frame_has_content(frame)

    def test_missing_font_returns_black_frame(self, helpers):
        frame = helpers.render_text("Hello", font_name="NONEXISTENT")
        assert _frame_is_black(frame)


class TestDrawIcon:
    """Tests for draw_icon()."""

    def test_draws_pixels_on_frame(self, helpers):
        frame = helpers.create_frame()
        # Create a simple 8x8 icon (all pixels set)
        icon_data = b"\xff" * 8  # 8 bytes = 64 bits = 8x8 all set
        result = helpers.draw_icon(
            frame, icon_data, x=0, y=0, size=(8, 8), color=(255, 0, 0)
        )
        # Check that pixels were drawn
        assert result.getpixel((0, 0)) == (255, 0, 0)
        assert result.getpixel((7, 7)) == (255, 0, 0)

    def test_respects_icon_bounds(self, helpers):
        frame = helpers.create_frame()
        # 16x16 icon, all pixels set
        icon_data = b"\xff" * 32  # 16*16/8 = 32 bytes
        result = helpers.draw_icon(
            frame, icon_data, x=5, y=5, size=(16, 16), color=(0, 255, 0)
        )
        # Pixel at (5, 5) should be colored
        assert result.getpixel((5, 5)) == (0, 255, 0)
        # Pixel at (4, 4) should still be black
        assert result.getpixel((4, 4)) == (0, 0, 0)

    def test_clips_to_frame_bounds(self, helpers):
        frame = helpers.create_frame()
        # Place icon partially off-screen
        icon_data = b"\xff" * 32  # 16x16 all set
        # Should not raise even when icon extends beyond frame
        result = helpers.draw_icon(
            frame, icon_data, x=120, y=25, size=(16, 16), color=(0, 0, 255)
        )
        assert result.size == (128, 32)

    def test_empty_icon_data(self, helpers):
        frame = helpers.create_frame()
        # Empty icon data should not crash
        result = helpers.draw_icon(
            frame, b"", x=0, y=0, size=(16, 16), color=(255, 255, 255)
        )
        # Frame should remain black
        assert result.getpixel((0, 0)) == (0, 0, 0)


class TestCompositeFrames:
    """Tests for composite_frames()."""

    def test_black_foreground_is_transparent(self, helpers):
        bg = helpers.create_frame(color=(100, 100, 100))
        fg = helpers.create_frame(color=(0, 0, 0))
        result = helpers.composite_frames(bg, fg)
        # Background should show through
        assert result.getpixel((64, 16)) == (100, 100, 100)

    def test_non_black_foreground_overwrites(self, helpers):
        bg = helpers.create_frame(color=(100, 100, 100))
        fg = helpers.create_frame(color=(255, 0, 0))
        result = helpers.composite_frames(bg, fg)
        # Foreground should overwrite
        assert result.getpixel((64, 16)) == (255, 0, 0)

    def test_partial_foreground(self, helpers):
        bg = helpers.create_frame(color=(50, 50, 50))
        fg = helpers.create_frame(color=(0, 0, 0))
        # Set a single pixel in foreground
        fg.putpixel((10, 10), (200, 200, 200))
        result = helpers.composite_frames(bg, fg)
        # That pixel should be from foreground
        assert result.getpixel((10, 10)) == (200, 200, 200)
        # Other pixels should be from background
        assert result.getpixel((0, 0)) == (50, 50, 50)

    def test_returns_same_mode(self, helpers):
        bg = helpers.create_frame()
        fg = helpers.create_frame()
        result = helpers.composite_frames(bg, fg)
        assert result.mode == "RGB"


@requires_fonts
class TestGetFontNames:
    """Tests for get_font_names()."""

    def test_returns_list(self, helpers):
        names = helpers.get_font_names()
        assert isinstance(names, list)

    def test_finds_standard_font(self, helpers):
        names = helpers.get_font_names()
        assert "STANDARD" in names

    def test_finds_multiple_fonts(self, helpers):
        names = helpers.get_font_names()
        # DotClk/Fonts has STANDARD, MENU, SYSTEM
        assert len(names) >= 3

    def test_no_extension_in_names(self, helpers):
        names = helpers.get_font_names()
        for name in names:
            assert not name.endswith(".fnt")

    def test_empty_directory(self):
        """Test with a non-existent resources path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            h = PluginHelpers(128, 32, Path(tmpdir))
            names = h.get_font_names()
            assert names == []


@requires_fonts
class TestGetTextWidth:
    """Tests for get_text_width()."""

    def test_empty_text_returns_zero(self, helpers):
        assert helpers.get_text_width("") == 0

    def test_non_empty_text_returns_positive(self, helpers):
        width = helpers.get_text_width("Hello")
        assert width > 0

    def test_longer_text_is_wider(self, helpers):
        w1 = helpers.get_text_width("Hi")
        w2 = helpers.get_text_width("Hello World")
        assert w2 > w1

    def test_missing_font_returns_zero(self, helpers):
        assert helpers.get_text_width("Hello", font_name="NONEXISTENT") == 0

    def test_single_char_width(self, helpers):
        width = helpers.get_text_width("A")
        assert width > 0


# Feature: plugin-system, Property 18: PluginHelpers Text Width Consistency
@requires_fonts
class TestTextWidthConsistencyProperty:
    """Property 18: PluginHelpers Text Width Consistency.

    For any string and font name, PluginHelpers.get_text_width(text, font)
    SHALL return a value equal to the actual pixel width of the rendered text
    image produced by render_text(text, font_name=font).

    **Validates: Requirements 6.8**
    """

    # Characters available in STANDARD font
    STANDARD_CHARS = "0123456789:/AMP"
    # Characters available in MENU font (broader set)
    MENU_CHARS = " &+-./0123456789:<>ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    @staticmethod
    def _make_helpers():
        resources_path = Path(__file__).parent.parent / "DotClk"
        return PluginHelpers(width=128, height=32, resources_path=resources_path)

    @given(
        text=st.text(
            alphabet="0123456789:/AMP",
            min_size=1,
            max_size=8,
        )
    )
    @settings(max_examples=100)
    def test_text_width_matches_rendered_width_standard(self, text):
        """get_text_width matches actual rendered pixel width for STANDARD font.

        **Validates: Requirements 6.8**
        """
        helpers = self._make_helpers()
        predicted_width = helpers.get_text_width(text, font_name="STANDARD")

        # Render text at x=0 (non-centered) to measure actual content width
        frame = helpers.render_text(text, x=0, y=0, font_name="STANDARD")

        # Find the rightmost non-black column (actual rendered width)
        actual_width = _rightmost_content_column(frame) + 1

        if actual_width == 0:
            # No visible content rendered - width should still be consistent
            assert predicted_width >= 0
            return

        # The predicted width should equal the actual rendered content width
        assert predicted_width == actual_width, (
            f"Text '{text}': get_text_width={predicted_width}, "
            f"actual rendered width={actual_width}"
        )

    @given(
        text=st.text(
            alphabet=" &+-./0123456789:<>ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=1,
            max_size=8,
        )
    )
    @settings(max_examples=100)
    def test_text_width_matches_rendered_width_menu(self, text):
        """get_text_width matches actual rendered pixel width for MENU font.

        **Validates: Requirements 6.8**
        """
        helpers = self._make_helpers()
        predicted_width = helpers.get_text_width(text, font_name="MENU")

        # Render text at x=0 (non-centered) to measure actual content width
        frame = helpers.render_text(text, x=0, y=0, font_name="MENU")

        actual_width = _rightmost_content_column(frame) + 1

        if actual_width == 0:
            assert predicted_width >= 0
            return

        assert predicted_width == actual_width, (
            f"Text '{text}': get_text_width={predicted_width}, "
            f"actual rendered width={actual_width}"
        )

    @given(
        text=st.text(
            alphabet="0123456789:/AMP",
            min_size=1,
            max_size=8,
        ),
        font_name=st.sampled_from(["STANDARD", "MENU", "SYSTEM"]),
    )
    @settings(max_examples=100)
    def test_text_width_bounds_rendered_content(self, text, font_name):
        """Rendered content never exceeds get_text_width for any font.

        **Validates: Requirements 6.8**
        """
        helpers = self._make_helpers()
        predicted_width = helpers.get_text_width(text, font_name=font_name)

        # Skip if font doesn't exist or text is empty
        assume(predicted_width > 0)

        # Render text at x=0
        frame = helpers.render_text(text, x=0, y=0, font_name=font_name)

        actual_width = _rightmost_content_column(frame) + 1

        if actual_width == 0:
            return  # No visible content, nothing to check

        # Rendered content should not exceed predicted width
        assert actual_width <= predicted_width, (
            f"Text '{text}' with font '{font_name}': rendered width "
            f"{actual_width} exceeds get_text_width {predicted_width}"
        )
