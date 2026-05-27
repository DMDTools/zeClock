"""Property tests for plugin discovery correctness.

**Property 2: Plugin Discovery Correctness**
**Validates: Requirements 1.1, 1.2, 1.3**

For any set of Python files in the plugin directories, the Plugin_Manager SHALL
register exactly those files that contain a class implementing the ClockPlugin
interface with a valid name. Files that fail to import or contain no valid plugin
class SHALL be skipped without affecting the loading of other plugins.
"""

import logging
import tempfile
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import PLUGIN_NAME_PATTERN


# --- Strategies for generating plugin file content ---

def valid_plugin_name_strategy():
    """Generate valid plugin names matching ^[a-z0-9_-]{1,64}$."""
    return st.from_regex(r"^[a-z0-9_-]{1,64}$", fullmatch=True)


def valid_plugin_file_content(name: str) -> str:
    """Generate a valid plugin file with the given name."""
    return f'''"""Auto-generated valid plugin: {name}."""
from typing import Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin


class GeneratedPlugin(ClockPlugin):
    """A valid generated plugin."""

    @property
    def name(self) -> str:
        return "{name}"

    @property
    def description(self) -> str:
        return "Generated test plugin"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass
'''


def invalid_plugin_file_syntax_error() -> str:
    """Generate a Python file with a syntax error."""
    return "def broken(\n    # missing closing paren and colon\n"


def invalid_plugin_file_import_error() -> str:
    """Generate a Python file that raises ImportError."""
    return "import nonexistent_module_xyz_12345\n"


def invalid_plugin_file_no_class() -> str:
    """Generate a Python file with no ClockPlugin subclass."""
    return '"""A module with no plugin class."""\n\ndef some_function():\n    return 42\n'


def invalid_plugin_file_abstract_class() -> str:
    """Generate a Python file with an abstract (incomplete) ClockPlugin subclass."""
    return '''"""A module with an abstract plugin class."""
from zeclock.plugins.base import ClockPlugin


class IncompletePlugin(ClockPlugin):
    """Missing required abstract methods."""
    pass
'''


def invalid_name_plugin_file(bad_name: str) -> str:
    """Generate a plugin file with an invalid name."""
    # Escape the bad_name for use in a Python string
    escaped = bad_name.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'''"""Plugin with invalid name."""
from typing import Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin


class BadNamePlugin(ClockPlugin):
    @property
    def name(self) -> str:
        return "{escaped}"

    @property
    def description(self) -> str:
        return "Plugin with bad name"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass
'''


# Strategy for generating a mix of valid and invalid plugin files
@st.composite
def plugin_file_set(draw):
    """Generate a set of plugin files: some valid, some invalid.

    Returns a list of (filename, content, is_valid, expected_name) tuples.
    """
    # Generate 1-5 valid plugins with unique names
    num_valid = draw(st.integers(min_value=0, max_value=5))
    valid_names = draw(
        st.lists(
            valid_plugin_name_strategy(),
            min_size=num_valid,
            max_size=num_valid,
            unique=True,
        )
    )

    files: List[Tuple[str, str, bool, str]] = []
    used_filenames = set()

    for i, name in enumerate(valid_names):
        filename = f"valid_plugin_{i}.py"
        used_filenames.add(filename)
        content = valid_plugin_file_content(name)
        files.append((filename, content, True, name))

    # Generate 0-3 invalid files of various types
    num_invalid = draw(st.integers(min_value=0, max_value=3))
    invalid_generators = [
        invalid_plugin_file_syntax_error,
        invalid_plugin_file_import_error,
        invalid_plugin_file_no_class,
        invalid_plugin_file_abstract_class,
    ]

    for i in range(num_invalid):
        filename = f"invalid_plugin_{i}.py"
        used_filenames.add(filename)
        gen = draw(st.sampled_from(invalid_generators))
        content = gen()
        files.append((filename, content, False, ""))

    return files


# --- Property Tests ---

# Feature: plugin-system, Property 2: Plugin Discovery Correctness


class TestPluginDiscoveryCorrectness:
    """Property tests verifying plugin discovery registers exactly valid plugins."""

    @given(file_set=plugin_file_set())
    @settings(max_examples=50, deadline=30000)
    @pytest.mark.asyncio
    async def test_discovery_registers_exactly_valid_plugins(self, file_set):
        """For any set of plugin files, only valid ones are registered.

        **Validates: Requirements 1.1, 1.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            expected_names = set()

            for filename, content, is_valid, expected_name in file_set:
                filepath = plugin_dir / filename
                filepath.write_text(content)
                if is_valid:
                    expected_names.add(expected_name)

            # Create a PluginManager and load from the temp directory
            manager = PluginManager(width=128, height=32)

            # Patch the user plugin dir and built-in dir to use our temp dirs
            empty_dir = Path(tmpdir) / "empty_builtin"
            empty_dir.mkdir()

            with patch.object(manager.config, "load"):
                manager._load_plugins_from_directory(plugin_dir, source="user")

            # Verify exactly the valid plugins were registered
            registered_names = set()
            for entry in manager.registry.get_all_plugins():
                registered_names.add(entry.name)

            assert registered_names == expected_names, (
                f"Expected {expected_names}, got {registered_names}"
            )

    @given(file_set=plugin_file_set())
    @settings(max_examples=50, deadline=30000)
    @pytest.mark.asyncio
    async def test_invalid_files_do_not_prevent_valid_loading(self, file_set):
        """Import errors in some files don't affect loading of other valid plugins.

        **Validates: Requirements 1.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            valid_count = 0
            for filename, content, is_valid, _ in file_set:
                filepath = plugin_dir / filename
                filepath.write_text(content)
                if is_valid:
                    valid_count += 1

            manager = PluginManager(width=128, height=32)

            with patch.object(manager.config, "load"):
                manager._load_plugins_from_directory(plugin_dir, source="user")

            # All valid plugins should be registered regardless of invalid ones
            registered = manager.registry.get_all_plugins()
            assert len(registered) == valid_count

    @given(name=valid_plugin_name_strategy())
    @settings(max_examples=50, deadline=30000)
    @pytest.mark.asyncio
    async def test_valid_plugin_always_registered(self, name):
        """Any file with a valid ClockPlugin implementation is always registered.

        **Validates: Requirements 1.1, 1.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            content = valid_plugin_file_content(name)
            filepath = plugin_dir / "test_plugin.py"
            filepath.write_text(content)

            manager = PluginManager(width=128, height=32)

            with patch.object(manager.config, "load"):
                manager._load_plugins_from_directory(plugin_dir, source="user")

            assert manager.registry.has_plugin(name), (
                f"Valid plugin '{name}' was not registered"
            )

    @pytest.mark.asyncio
    async def test_import_error_logged_and_skipped(self, caplog):
        """Files that fail to import are logged at WARNING and skipped.

        **Validates: Requirements 1.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            # Write a file that will cause an ImportError
            bad_file = plugin_dir / "bad_import.py"
            bad_file.write_text(invalid_plugin_file_import_error())

            # Write a valid plugin file
            good_file = plugin_dir / "good_plugin.py"
            good_file.write_text(valid_plugin_file_content("good-plugin"))

            manager = PluginManager(width=128, height=32)

            with caplog.at_level(logging.WARNING):
                with patch.object(manager.config, "load"):
                    manager._load_plugins_from_directory(plugin_dir, source="user")

            # The valid plugin should still be registered
            assert manager.registry.has_plugin("good-plugin")

            # A warning should have been logged for the bad file
            warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert any("bad_import.py" in msg for msg in warning_messages), (
                f"Expected warning about bad_import.py, got: {warning_messages}"
            )

    @pytest.mark.asyncio
    async def test_syntax_error_logged_and_skipped(self, caplog):
        """Files with syntax errors are logged at WARNING and skipped.

        **Validates: Requirements 1.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            # Write a file with syntax error
            bad_file = plugin_dir / "syntax_error.py"
            bad_file.write_text(invalid_plugin_file_syntax_error())

            # Write a valid plugin file
            good_file = plugin_dir / "good_plugin.py"
            good_file.write_text(valid_plugin_file_content("good-plugin"))

            manager = PluginManager(width=128, height=32)

            with caplog.at_level(logging.WARNING):
                with patch.object(manager.config, "load"):
                    manager._load_plugins_from_directory(plugin_dir, source="user")

            # The valid plugin should still be registered
            assert manager.registry.has_plugin("good-plugin")

            # A warning should have been logged for the syntax error file
            warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert any("syntax_error.py" in msg for msg in warning_messages), (
                f"Expected warning about syntax_error.py, got: {warning_messages}"
            )

    @pytest.mark.asyncio
    async def test_invalid_name_plugin_skipped(self, caplog):
        """Plugins with invalid names are logged at WARNING and skipped.

        **Validates: Requirements 1.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            # Write a plugin with an invalid name (uppercase)
            bad_name_file = plugin_dir / "bad_name_plugin.py"
            bad_name_file.write_text(invalid_name_plugin_file("INVALID_NAME"))

            # Write a valid plugin file
            good_file = plugin_dir / "good_plugin.py"
            good_file.write_text(valid_plugin_file_content("good-plugin"))

            manager = PluginManager(width=128, height=32)

            with caplog.at_level(logging.WARNING):
                with patch.object(manager.config, "load"):
                    manager._load_plugins_from_directory(plugin_dir, source="user")

            # The valid plugin should be registered
            assert manager.registry.has_plugin("good-plugin")

            # The invalid name plugin should NOT be registered
            assert not manager.registry.has_plugin("INVALID_NAME")

            # A warning should have been logged
            warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert any("invalid name" in msg.lower() or "INVALID_NAME" in msg for msg in warning_messages), (
                f"Expected warning about invalid name, got: {warning_messages}"
            )

    @pytest.mark.asyncio
    async def test_no_plugin_class_file_skipped(self):
        """Files without a ClockPlugin subclass are silently skipped.

        **Validates: Requirements 1.1**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            # Write a file with no plugin class
            no_class_file = plugin_dir / "no_class.py"
            no_class_file.write_text(invalid_plugin_file_no_class())

            manager = PluginManager(width=128, height=32)

            with patch.object(manager.config, "load"):
                manager._load_plugins_from_directory(plugin_dir, source="user")

            # Nothing should be registered
            assert len(manager.registry) == 0

    @pytest.mark.asyncio
    async def test_empty_directory_registers_nothing(self):
        """An empty plugin directory results in no registered plugins.

        **Validates: Requirements 1.1**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            manager = PluginManager(width=128, height=32)

            with patch.object(manager.config, "load"):
                manager._load_plugins_from_directory(plugin_dir, source="user")

            assert len(manager.registry) == 0
