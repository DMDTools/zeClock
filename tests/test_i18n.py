"""Tests for internationalization (i18n) of the web UI.

Validates:
- All translation keys are consistent across supported languages
- HTML data-i18n attributes reference valid translation keys
- i18n.js is syntactically valid JavaScript
- Language config propagation through PluginConfig
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).parent.parent / "zeclock" / "remote" / "web"
I18N_JS = WEB_DIR / "i18n.js"
INDEX_HTML = WEB_DIR / "index.html"
APP_JS = WEB_DIR / "app.js"

SUPPORTED_LANGUAGES = ("en", "fr", "de", "es")


def _extract_translation_keys(js_content: str) -> dict:
    """Extract translation keys per language from i18n.js content.

    Parses the JS object literals to find all "key": "value" entries
    for each language block.
    """
    keys_by_lang = {}
    # Find each language block: en: { ... }, fr: { ... }, etc.
    lang_pattern = re.compile(
        r"\b(" + "|".join(SUPPORTED_LANGUAGES) + r")\s*:\s*\{", re.MULTILINE
    )

    positions = [(m.group(1), m.end()) for m in lang_pattern.finditer(js_content)]

    for i, (lang, start) in enumerate(positions):
        # Find matching closing brace by counting braces
        depth = 1
        pos = start
        while pos < len(js_content) and depth > 0:
            if js_content[pos] == "{":
                depth += 1
            elif js_content[pos] == "}":
                depth -= 1
            pos += 1
        block = js_content[start : pos - 1]

        # Extract keys from "key.subkey": "value" patterns
        key_pattern = re.compile(r'"([a-z][a-z0-9_.]+)":\s*"')
        keys_by_lang[lang] = set(m.group(1) for m in key_pattern.finditer(block))

    return keys_by_lang


def _extract_html_i18n_keys(html_content: str) -> set:
    """Extract all data-i18n, data-i18n-placeholder, data-i18n-title keys from HTML."""
    keys = set()
    for attr in ("data-i18n", "data-i18n-placeholder", "data-i18n-title"):
        pattern = re.compile(rf'{attr}="([^"]+)"')
        keys.update(m.group(1) for m in pattern.finditer(html_content))
    return keys


def _extract_t_calls(js_content: str) -> set:
    """Extract all t('key') and t("key") calls from JavaScript."""
    pattern = re.compile(r"""\bt\(\s*['"]([a-z][a-z0-9_.]+)['"]\s*[,)]""")
    return set(m.group(1) for m in pattern.finditer(js_content))


class TestI18nFileValidity:
    """Test that i18n.js is syntactically valid."""

    def test_i18n_js_exists(self):
        assert I18N_JS.exists(), "i18n.js must exist in web directory"

    def test_i18n_js_syntax(self):
        """Verify i18n.js passes Node.js syntax check."""
        result = subprocess.run(
            ["node", "--check", str(I18N_JS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in i18n.js: {result.stderr}"

    def test_app_js_syntax(self):
        """Verify app.js passes Node.js syntax check."""
        result = subprocess.run(
            ["node", "--check", str(APP_JS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in app.js: {result.stderr}"


class TestTranslationConsistency:
    """Test that all languages have the same set of keys."""

    @pytest.fixture
    def keys_by_lang(self):
        content = I18N_JS.read_text()
        return _extract_translation_keys(content)

    def test_all_languages_present(self, keys_by_lang):
        """All supported languages must have a translation block."""
        for lang in SUPPORTED_LANGUAGES:
            assert lang in keys_by_lang, f"Missing translation block for '{lang}'"

    def test_english_has_keys(self, keys_by_lang):
        """English (reference) must have translation keys."""
        assert len(keys_by_lang["en"]) > 0, "English has no translation keys"

    @pytest.mark.parametrize("lang", ["fr", "de", "es"])
    def test_language_has_all_english_keys(self, keys_by_lang, lang):
        """Each language must have all keys present in English."""
        en_keys = keys_by_lang["en"]
        lang_keys = keys_by_lang.get(lang, set())
        missing = en_keys - lang_keys
        assert not missing, (
            f"Language '{lang}' is missing {len(missing)} key(s): "
            f"{sorted(missing)[:10]}"
        )

    @pytest.mark.parametrize("lang", ["fr", "de", "es"])
    def test_no_extra_keys(self, keys_by_lang, lang):
        """Languages should not have keys that don't exist in English."""
        en_keys = keys_by_lang["en"]
        lang_keys = keys_by_lang.get(lang, set())
        extra = lang_keys - en_keys
        assert not extra, (
            f"Language '{lang}' has {len(extra)} extra key(s) not in English: "
            f"{sorted(extra)[:10]}"
        )


class TestHtmlI18nAttributes:
    """Test that HTML data-i18n attributes reference valid keys."""

    @pytest.fixture
    def en_keys(self):
        content = I18N_JS.read_text()
        keys = _extract_translation_keys(content)
        return keys.get("en", set())

    @pytest.fixture
    def html_keys(self):
        content = INDEX_HTML.read_text()
        return _extract_html_i18n_keys(content)

    def test_all_html_keys_exist_in_translations(self, html_keys, en_keys):
        """Every data-i18n key in HTML must exist in the English translations."""
        missing = html_keys - en_keys
        assert not missing, (
            f"HTML references {len(missing)} undefined i18n key(s): "
            f"{sorted(missing)[:10]}"
        )

    def test_html_has_i18n_attributes(self, html_keys):
        """HTML must have at least some data-i18n attributes (sanity check)."""
        assert (
            len(html_keys) >= 20
        ), f"Expected at least 20 data-i18n attributes, found {len(html_keys)}"


class TestJsI18nCalls:
    """Test that t() calls in app.js reference valid keys."""

    @pytest.fixture
    def en_keys(self):
        content = I18N_JS.read_text()
        keys = _extract_translation_keys(content)
        return keys.get("en", set())

    @pytest.fixture
    def t_keys(self):
        content = APP_JS.read_text()
        return _extract_t_calls(content)

    def test_all_t_calls_reference_valid_keys(self, t_keys, en_keys):
        """Every t('key') call in app.js must reference a valid English key."""
        missing = t_keys - en_keys
        assert not missing, (
            f"app.js calls t() with {len(missing)} undefined key(s): "
            f"{sorted(missing)[:10]}"
        )

    def test_app_js_uses_t_calls(self, t_keys):
        """app.js must use t() for at least some strings (sanity check)."""
        assert (
            len(t_keys) >= 5
        ), f"Expected at least 5 t() calls in app.js, found {len(t_keys)}"


class TestI18nScriptLoading:
    """Test that index.html loads i18n.js before app.js."""

    def test_i18n_loaded_before_app(self):
        content = INDEX_HTML.read_text()
        i18n_pos = content.find('src="i18n.js"')
        app_pos = content.find('src="app.js"')
        assert i18n_pos > 0, "i18n.js script tag not found in HTML"
        assert app_pos > 0, "app.js script tag not found in HTML"
        assert i18n_pos < app_pos, "i18n.js must be loaded before app.js"


class TestPluginConfigLanguage:
    """Test that PluginConfig propagates language as a global setting."""

    def test_default_language_is_english(self, tmp_path):
        """When no language is set, default to English."""
        from zeclock.plugin_config import PluginConfig

        config = PluginConfig(config_path=tmp_path / "plugins.yaml")
        config.load()
        assert config.language == "en"

    def test_language_loaded_from_yaml(self, tmp_path):
        """Language set in YAML is properly loaded."""
        import yaml
        from zeclock.plugin_config import PluginConfig

        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "language": "fr",
                    "plugins": [{"name": "clock", "frequency": 0}],
                }
            )
        )
        config = PluginConfig(config_path=config_path)
        config.load()
        assert config.language == "fr"

    def test_language_injected_into_plugin_settings(self, tmp_path):
        """Global language is injected into every plugin's settings."""
        import yaml
        from zeclock.plugin_config import PluginConfig

        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "language": "de",
                    "plugins": [
                        {
                            "name": "weather",
                            "frequency": 50,
                            "settings": {"city": "Berlin"},
                        },
                    ],
                }
            )
        )
        config = PluginConfig(config_path=config_path)
        config.load()
        settings = config.get_plugin_config("weather")
        assert settings["language"] == "de"
        assert settings["city"] == "Berlin"

    def test_per_plugin_language_override_stripped(self, tmp_path):
        """Per-plugin language overrides are stripped (language is global only)."""
        import yaml
        from zeclock.plugin_config import PluginConfig

        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "language": "es",
                    "plugins": [
                        {
                            "name": "weather",
                            "frequency": 50,
                            "settings": {"language": "fr", "city": "Madrid"},
                        },
                    ],
                }
            )
        )
        config = PluginConfig(config_path=config_path)
        config.load()
        settings = config.get_plugin_config("weather")
        # Global language wins, per-plugin override is stripped
        assert settings["language"] == "es"

    def test_unknown_plugin_gets_language(self, tmp_path):
        """Even plugins not in config get the global language."""
        import yaml
        from zeclock.plugin_config import PluginConfig

        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "language": "fr",
                    "plugins": [{"name": "clock", "frequency": 0}],
                }
            )
        )
        config = PluginConfig(config_path=config_path)
        config.load()
        settings = config.get_plugin_config("nonexistent")
        assert settings == {"language": "fr"}
