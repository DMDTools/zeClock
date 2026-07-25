"""Tests for the render_alert and _word_wrap methods in PluginHelpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from zeclock.plugins.helpers import PluginHelpers


@pytest.fixture
def helpers(tmp_path):
    """Create a PluginHelpers instance with standard test dimensions."""
    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()
    return PluginHelpers(128, 32, tmp_path)


@pytest.fixture
def helpers_hd(tmp_path):
    """Create a PluginHelpers instance with HD dimensions."""
    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()
    return PluginHelpers(256, 64, tmp_path)


class TestRenderAlert:
    """Tests for PluginHelpers.render_alert()."""

    def test_returns_rgb_image_with_correct_dimensions(self, helpers):
        """render_alert returns an RGB image with the display dimensions."""
        frame = helpers.render_alert("TEST ALERT", frame_index=0)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    def test_returns_correct_dimensions_hd(self, helpers_hd):
        """render_alert works with HD dimensions."""
        frame = helpers_hd.render_alert("TEST ALERT", frame_index=0)
        assert frame.mode == "RGB"
        assert frame.size == (256, 64)

    def test_border_visible_on_blink_on_frame(self, helpers):
        """Border pixels are colored when blink is on (even cycle)."""
        frame = helpers.render_alert(
            "X",
            frame_index=0,
            border_color=(255, 0, 0),
            blink_interval_frames=5,
        )
        pixels = frame.load()
        # Top-left corner pixel should be the border color
        assert pixels[0, 0] == (255, 0, 0)
        # Middle of top border
        assert pixels[64, 0] == (255, 0, 0)

    def test_border_hidden_on_blink_off_frame(self, helpers):
        """Border pixels are black when blink is off (odd cycle)."""
        # frame_index=5 with blink_interval_frames=5 means cycle 1 (odd = off)
        frame = helpers.render_alert(
            "X",
            frame_index=5,
            border_color=(255, 0, 0),
            blink_interval_frames=5,
        )
        pixels = frame.load()
        # Top-left corner should be black (border off)
        assert pixels[0, 0] == (0, 0, 0)

    def test_border_alternates(self, helpers):
        """Border alternates between visible and hidden."""
        frame_on = helpers.render_alert("X", frame_index=0, blink_interval_frames=3)
        frame_off = helpers.render_alert("X", frame_index=3, blink_interval_frames=3)
        pixels_on = frame_on.load()
        pixels_off = frame_off.load()
        # On frame: border visible
        assert pixels_on[0, 0] != (0, 0, 0)
        # Off frame: border hidden
        assert pixels_off[0, 0] == (0, 0, 0)

    def test_custom_border_color(self, helpers):
        """Custom border color is used."""
        frame = helpers.render_alert(
            "X",
            frame_index=0,
            border_color=(0, 255, 0),
            blink_interval_frames=100,
        )
        pixels = frame.load()
        assert pixels[0, 0] == (0, 255, 0)

    def test_border_width_3_pixels(self, helpers):
        """Default border width is 3 pixels deep."""
        frame = helpers.render_alert(
            "X",
            frame_index=0,
            border_color=(255, 0, 0),
            border_width=3,
            blink_interval_frames=100,
        )
        pixels = frame.load()
        # Pixel at depth 0, 1, 2 should be border
        assert pixels[0, 0] == (255, 0, 0)
        assert pixels[1, 1] == (255, 0, 0)
        assert pixels[2, 2] == (255, 0, 0)
        # Pixel at depth 3 should NOT be border (it's the gap or text area)
        # (it's either black background or text)
        assert pixels[3, 3] != (255, 0, 0)

    def test_empty_text_renders_without_error(self, helpers):
        """Empty text doesn't crash."""
        frame = helpers.render_alert("", frame_index=0)
        assert frame.size == (128, 32)

    def test_very_long_text_does_not_crash(self, helpers):
        """Very long text is wrapped without crashing."""
        long_text = "A " * 100
        frame = helpers.render_alert(long_text, frame_index=0)
        assert frame.size == (128, 32)


class TestWordWrap:
    """Tests for PluginHelpers._word_wrap()."""

    def _make_helpers_with_font(self, tmp_path, char_width=6):
        """Create helpers with a mocked font for predictable width measurement."""
        fonts_dir = tmp_path / "Fonts"
        fonts_dir.mkdir(exist_ok=True)
        h = PluginHelpers(128, 32, tmp_path)

        # Mock a font with fixed character width
        mock_font = MagicMock()
        mock_font.char_height = 10
        mock_font.name = "MOCK"
        mock_font.get_text_width = lambda text: len(text) * char_width
        h._fonts["STANDARD"] = mock_font
        return h

    def test_short_text_no_wrap(self, tmp_path):
        """Text that fits in one line is not wrapped."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        # 128px wide, 6px per char = 21 chars fit
        result = h._word_wrap("HELLO WORLD", 128, "STANDARD")
        assert result == "HELLO WORLD"

    def test_long_text_wraps_at_word_boundary(self, tmp_path):
        """Text wider than max_width wraps at word boundaries."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        # max_width=60px, 6px/char = 10 chars per line
        result = h._word_wrap("HELLO WORLD FOO", 60, "STANDARD")
        lines = result.split("\n")
        assert len(lines) >= 2
        # Each line should fit within 60px (10 chars)
        for line in lines:
            assert len(line) * 6 <= 60 or len(line.split()) == 1

    def test_single_long_word_stays_on_own_line(self, tmp_path):
        """A word wider than max_width gets its own line (not split mid-word)."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        # max_width=30px (5 chars), word is 10 chars
        result = h._word_wrap("ABCDEFGHIJ", 30, "STANDARD")
        # Single word, can't break — stays as-is on one line
        assert result == "ABCDEFGHIJ"

    def test_existing_newlines_preserved(self, tmp_path):
        """Existing newlines in text are preserved."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        result = h._word_wrap("LINE1\nLINE2", 128, "STANDARD")
        assert "LINE1" in result
        assert "LINE2" in result
        lines = result.split("\n")
        assert lines[0] == "LINE1"
        assert lines[1] == "LINE2"

    def test_empty_text(self, tmp_path):
        """Empty text returns empty string."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        result = h._word_wrap("", 128, "STANDARD")
        assert result == ""

    def test_multiple_spaces_treated_as_separators(self, tmp_path):
        """Multiple spaces between words are collapsed by split()."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        result = h._word_wrap("A    B    C", 128, "STANDARD")
        # split() collapses spaces
        assert result == "A B C"

    def test_wraps_correctly_with_narrow_width(self, tmp_path):
        """Each word ends up on its own line when width is very narrow."""
        h = self._make_helpers_with_font(tmp_path, char_width=6)
        # max_width=36px (6 chars) — "PERSONNE" is 8 chars, won't fit with another word
        result = h._word_wrap("PERSONNE DETECTEE", 36, "STANDARD")
        lines = result.split("\n")
        assert "PERSONNE" in lines
        assert "DETECTEE" in lines

    def test_no_font_returns_original_text(self, tmp_path):
        """If font is not found, returns original text unchanged."""
        fonts_dir = tmp_path / "Fonts"
        fonts_dir.mkdir(exist_ok=True)
        h = PluginHelpers(128, 32, tmp_path)
        # No fonts loaded — _get_font returns None
        result = h._word_wrap("HELLO WORLD", 60, "NONEXISTENT")
        assert result == "HELLO WORLD"


class TestRenderAlertWithIcon:
    """Tests for render_alert with icon parameter."""

    def test_icon_parameter_accepted(self, helpers):
        """render_alert accepts icon parameter without error."""
        frame = helpers.render_alert("ALERT", frame_index=0, icon="beacon")
        assert frame.size == (128, 32)

    def test_unknown_icon_does_not_crash(self, helpers):
        """Unknown icon name doesn't crash (gracefully ignored)."""
        frame = helpers.render_alert("ALERT", frame_index=0, icon="nonexistent")
        assert frame.size == (128, 32)

    def test_none_icon_same_as_no_icon(self, helpers):
        """icon=None produces same result as no icon parameter."""
        frame_no_icon = helpers.render_alert("ALERT", frame_index=0)
        frame_none = helpers.render_alert("ALERT", frame_index=0, icon=None)
        assert frame_no_icon.tobytes() == frame_none.tobytes()

    def test_icon_with_real_alert_icons_module(self, helpers):
        """Test with the actual alert_icons module (if available)."""
        try:
            from zeclock.plugins.alert_icons import get_alert_icon

            icon = get_alert_icon("beacon", hd=False)
            assert icon is not None
            assert icon.size == (16, 16)
            assert icon.mode == "RGB"
        except ImportError:
            pytest.skip("alert_icons module not generated")

    def test_all_detection_icons_available(self):
        """All detection type icons exist in the alert_icons module."""
        try:
            from zeclock.plugins.alert_icons import get_alert_icon

            for name in ("beacon", "person", "vehicle", "animal", "motion", "warning"):
                icon = get_alert_icon(name, hd=False)
                assert icon is not None, f"Icon '{name}' not found"
                assert icon.size == (16, 16)
        except ImportError:
            pytest.skip("alert_icons module not generated")

    def test_hd_icons_are_32x32(self):
        """HD icons are 32x32."""
        try:
            from zeclock.plugins.alert_icons import get_alert_icon

            icon = get_alert_icon("beacon", hd=True)
            assert icon is not None
            assert icon.size == (32, 32)
        except ImportError:
            pytest.skip("alert_icons module not generated")
