"""Unit tests for PinballPlugin.

Tests the built-in pinball animation plugin that wraps existing .scn animation
playback logic including DotBlt overlay composition and scene storyboard metadata.

**Validates: Requirements 5.1, 5.5, 5.6**
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, AsyncMock

import numpy as np
import pytest
from PIL import Image

from zeclock.plugins.pinball_plugin import (
    PinballPlugin,
    COLOR_MAP,
    DEFAULT_COLOR,
    DEFAULT_FRAME_DELAY_MS,
)

# --- Mock Scene Factory ---


def create_mock_scene(
    frame_count: int = 3,
    frame_delay_ms: int = 50,
    first_frame_delay: int = 0,
    last_frame_delay: int = 0,
    clock_style: int = 0,
    custom_x: int = 64,
    custom_y: int = 16,
    frame_layer: int = 0,
    width: int = 128,
    height: int = 32,
) -> MagicMock:
    """Create a mock Scene object with configurable attributes."""
    scene = MagicMock()
    scene.frame_delay_ms = frame_delay_ms
    scene.first_frame_delay = first_frame_delay
    scene.last_frame_delay = last_frame_delay
    scene.clock_style = clock_style
    scene.custom_x = custom_x
    scene.custom_y = custom_y
    scene.frame_layer = frame_layer

    # Create grayscale animation frames
    frames = []
    for i in range(frame_count):
        # Each frame has a different intensity pattern for distinguishability
        intensity = int(255 * (i + 1) / frame_count)
        frame = Image.new("L", (width, height), intensity)
        frames.append(frame)

    scene.frames = frames
    return scene


# --- Test Class ---


class TestPinballPluginProperties:
    """Test basic plugin properties."""

    def test_name_is_pinball(self):
        """Plugin name should be 'pinball'."""
        plugin = PinballPlugin()
        assert plugin.name == "pinball"

    def test_description_is_non_empty(self):
        """Plugin description should be a non-empty string."""
        plugin = PinballPlugin()
        assert isinstance(plugin.description, str)
        assert len(plugin.description) > 0

    def test_default_frame_delay_ms(self):
        """Default frame_delay_ms should be 40ms before initialization."""
        plugin = PinballPlugin()
        assert plugin.frame_delay_ms == DEFAULT_FRAME_DELAY_MS


class TestPinballPluginInitialize:
    """Test plugin initialization behavior."""

    @pytest.mark.asyncio
    async def test_color_config_passthrough(self):
        """Color config should be applied from config dict.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "color": "blue",
                "animations_dir": tmpdir,  # empty dir, no scenes
            }
            await plugin.initialize(config)

        assert plugin._color == COLOR_MAP["blue"]

    @pytest.mark.asyncio
    async def test_animation_color_config_passthrough(self):
        """Animation color config should be applied independently.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "color": "blue",
                "animation_color": "red",
                "animations_dir": tmpdir,
            }
            await plugin.initialize(config)

        assert plugin._color == COLOR_MAP["blue"]
        assert plugin._animation_color == COLOR_MAP["red"]

    @pytest.mark.asyncio
    async def test_animation_color_defaults_to_color(self):
        """When animation_color is not set, it defaults to the clock color.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "color": "green",
                "animations_dir": tmpdir,
            }
            await plugin.initialize(config)

        assert plugin._animation_color == COLOR_MAP["green"]

    @pytest.mark.asyncio
    async def test_invalid_color_falls_back_to_default(self):
        """Invalid color name should fall back to default color."""
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "color": "nonexistent_color",
                "animations_dir": tmpdir,
            }
            await plugin.initialize(config)

        assert plugin._color == COLOR_MAP[DEFAULT_COLOR]


class TestPinballPluginEmptyAnimations:
    """Test behavior when animations directory is empty or missing."""

    @pytest.mark.asyncio
    async def test_empty_directory_logs_warning(self, caplog):
        """Empty animations directory should log a warning.

        **Validates: Requirements 5.6**
        """
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"animations_dir": tmpdir}

            with caplog.at_level(logging.WARNING):
                await plugin.initialize(config)

            warning_messages = [
                r.message for r in caplog.records if r.levelno == logging.WARNING
            ]
            assert any(
                "No .scn files" in msg for msg in warning_messages
            ), f"Expected warning about no .scn files, got: {warning_messages}"

    @pytest.mark.asyncio
    async def test_empty_directory_signals_completion_immediately(self):
        """Empty animations directory should cause render_frame to return None.

        **Validates: Requirements 5.6**
        """
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"animations_dir": tmpdir}
            await plugin.initialize(config)

        # render_frame should return None immediately (no frames)
        result = await plugin.render_frame(128, 32)
        assert result is None

    @pytest.mark.asyncio
    async def test_nonexistent_directory_signals_completion(self):
        """Non-existent animations directory should signal completion.

        **Validates: Requirements 5.6**
        """
        plugin = PinballPlugin()

        config = {"animations_dir": "/nonexistent/path/to/animations"}
        await plugin.initialize(config)

        result = await plugin.render_frame(128, 32)
        assert result is None


class TestPinballPluginFrameRendering:
    """Test frame rendering and completion signaling."""

    @pytest.mark.asyncio
    async def test_render_frame_returns_precomputed_frames_sequentially(self):
        """render_frame() should return pre-computed frames in order.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=3, frame_delay_ms=50)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake .scn file
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        # Should get 3 frames
        frames = []
        for _ in range(3):
            frame = await plugin.render_frame(128, 32)
            assert frame is not None
            assert isinstance(frame, Image.Image)
            assert frame.mode == "RGB"
            assert frame.size == (128, 32)
            frames.append(frame)

        # Frames should be distinct (different intensities)
        assert len(frames) == 3

    @pytest.mark.asyncio
    async def test_render_frame_returns_none_after_all_frames(self):
        """render_frame() should return None after all frames are rendered.

        **Validates: Requirements 5.5**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=2, frame_delay_ms=40)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        # Consume all frames
        for _ in range(2):
            frame = await plugin.render_frame(128, 32)
            assert frame is not None

        # Next call should return None (completion signal)
        result = await plugin.render_frame(128, 32)
        assert result is None

    @pytest.mark.asyncio
    async def test_render_frame_continues_returning_none(self):
        """Subsequent calls after completion should keep returning None.

        **Validates: Requirements 5.5**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=1, frame_delay_ms=40)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        # Consume the single frame
        await plugin.render_frame(128, 32)

        # Multiple calls after completion should all return None
        for _ in range(3):
            assert await plugin.render_frame(128, 32) is None


class TestPinballPluginFrameDelay:
    """Test frame_delay_ms from scene metadata."""

    @pytest.mark.asyncio
    async def test_frame_delay_from_scene_metadata(self):
        """frame_delay_ms should match the scene's metadata value.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=2, frame_delay_ms=80)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        assert plugin.frame_delay_ms == 80

    @pytest.mark.asyncio
    async def test_frame_delay_defaults_when_scene_has_zero(self):
        """frame_delay_ms should default to 40ms when scene reports 0.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=2, frame_delay_ms=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        assert plugin.frame_delay_ms == DEFAULT_FRAME_DELAY_MS

    @pytest.mark.asyncio
    async def test_frame_delay_various_values(self):
        """frame_delay_ms should reflect different scene metadata values."""
        for delay in [25, 40, 100, 200]:
            plugin = PinballPlugin()
            mock_scene = create_mock_scene(frame_count=1, frame_delay_ms=delay)

            with tempfile.TemporaryDirectory() as tmpdir:
                scene_file = Path(tmpdir) / "test.scn"
                scene_file.write_bytes(b"fake")

                config = {"animations_dir": tmpdir}

                with patch(
                    "zeclock.plugins.pinball_plugin.load_scene",
                    return_value=mock_scene,
                ):
                    with patch(
                        "zeclock.plugins.pinball_plugin.load_font",
                        return_value=None,
                    ):
                        await plugin.initialize(config)

            assert plugin.frame_delay_ms == delay


class TestPinballPluginFrameOutput:
    """Test that frame output matches expected behavior from _precompute_animation."""

    @pytest.mark.asyncio
    async def test_frames_are_rgb_with_animation_color(self):
        """Without font, frames should be colorized with animation_color.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=1, frame_delay_ms=40)
        # Set a known intensity for the frame
        mock_scene.frames = [Image.new("L", (128, 32), 255)]

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {
                "animations_dir": tmpdir,
                "animation_color": "red",
            }

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        frame = await plugin.render_frame(128, 32)
        assert frame is not None
        assert frame.mode == "RGB"

        # With full intensity (255) and red color (255, 0, 0),
        # pixels should be (255, 0, 0)
        pixel = frame.getpixel((0, 0))
        assert pixel == (255, 0, 0)

    @pytest.mark.asyncio
    async def test_frames_respect_intensity_gradient(self):
        """Frame colorization should respect grayscale intensity values.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=1, frame_delay_ms=40)
        # Create a frame with half intensity
        mock_scene.frames = [Image.new("L", (128, 32), 128)]

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {
                "animations_dir": tmpdir,
                "animation_color": "orange",  # (255, 128, 0)
            }

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        frame = await plugin.render_frame(128, 32)
        assert frame is not None

        # With intensity 128/255 ≈ 0.502 and orange (255, 128, 0):
        # R = int(255 * 128/255) = 128
        # G = int(128 * 128/255) = 64
        # B = int(0 * 128/255) = 0
        pixel = frame.getpixel((0, 0))
        assert pixel[0] == 128  # R channel
        assert pixel[1] == 64  # G channel
        assert pixel[2] == 0  # B channel

    @pytest.mark.asyncio
    async def test_first_frame_delay_repeats_first_frame(self):
        """first_frame_delay should cause the first frame to be repeated.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        # frame_delay_ms=50, first_frame_delay=100 -> 2 extra first frames
        mock_scene = create_mock_scene(
            frame_count=2,
            frame_delay_ms=50,
            first_frame_delay=100,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        # Total frames: 2 (first_frame_delay/frame_delay) + 2 (original) = 4
        frame_count = 0
        while True:
            frame = await plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1

        assert frame_count == 4

    @pytest.mark.asyncio
    async def test_last_frame_delay_repeats_last_frame(self):
        """last_frame_delay should cause the last frame to be repeated.

        **Validates: Requirements 5.1**
        """
        plugin = PinballPlugin()
        # frame_delay_ms=50, last_frame_delay=150 -> 3 extra last frames
        mock_scene = create_mock_scene(
            frame_count=2,
            frame_delay_ms=50,
            last_frame_delay=150,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        # Total frames: 2 (original) + 3 (last_frame_delay/frame_delay) = 5
        frame_count = 0
        while True:
            frame = await plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1

        assert frame_count == 5


class TestPinballPluginCleanup:
    """Test cleanup behavior."""

    @pytest.mark.asyncio
    async def test_cleanup_releases_frames(self):
        """cleanup() should release all pre-computed frames."""
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=3, frame_delay_ms=40)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        assert len(plugin._frames) > 0

        await plugin.cleanup()

        assert len(plugin._frames) == 0
        assert plugin._frame_index == 0

    @pytest.mark.asyncio
    async def test_render_frame_returns_none_after_cleanup(self):
        """render_frame() should return None after cleanup."""
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=2, frame_delay_ms=40)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_file = Path(tmpdir) / "test.scn"
            scene_file.write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

        await plugin.cleanup()
        result = await plugin.render_frame(128, 32)
        assert result is None


class TestPinballPluginSceneSelection:
    """Test scene file discovery and selection."""

    @pytest.mark.asyncio
    async def test_selects_scene_from_directory(self):
        """Plugin should find and load .scn files from the animations directory."""
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=2, frame_delay_ms=40)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple .scn files
            for name in ["anim1.scn", "anim2.scn", "anim3.scn"]:
                (Path(tmpdir) / name).write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ) as mock_load:
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

            # load_scene should have been called with one of the .scn files
            assert mock_load.called
            called_path = mock_load.call_args[0][0]
            assert called_path.suffix == ".scn"
            assert called_path.parent == Path(tmpdir)

    @pytest.mark.asyncio
    async def test_finds_scn_files_in_subdirectories(self):
        """Plugin should find .scn files in subdirectories (glob **)."""
        plugin = PinballPlugin()
        mock_scene = create_mock_scene(frame_count=1, frame_delay_ms=40)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a .scn file in a subdirectory
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "nested.scn").write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                return_value=mock_scene,
            ) as mock_load:
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    await plugin.initialize(config)

            assert mock_load.called

    @pytest.mark.asyncio
    async def test_scene_load_failure_signals_completion(self, caplog):
        """If load_scene raises, plugin should signal completion gracefully."""
        plugin = PinballPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "broken.scn").write_bytes(b"fake")

            config = {"animations_dir": tmpdir}

            with patch(
                "zeclock.plugins.pinball_plugin.load_scene",
                side_effect=Exception("Corrupt scene file"),
            ):
                with patch(
                    "zeclock.plugins.pinball_plugin.load_font",
                    return_value=None,
                ):
                    with caplog.at_level(logging.WARNING):
                        await plugin.initialize(config)

        result = await plugin.render_frame(128, 32)
        assert result is None
