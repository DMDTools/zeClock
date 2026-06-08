"""Resource path resolution for zeClock.

Fonts are bundled in the package (zeclock/resources/fonts/) and also
installed to the data directory resources/Fonts/ during bootstrap.
The bundled fonts take priority so zeClock works without running --bootstrap first.
"""

from pathlib import Path


def get_fonts_dir() -> Path:
    """Get the fonts directory, preferring bundled package fonts.

    Resolution order:
    1. Bundled fonts in the zeclock package (zeclock/resources/fonts/)
    2. User-installed fonts (<data_dir>/resources/Fonts/)

    Returns:
        Path to the directory containing .fnt files.
    """
    # Bundled fonts (always available after pip install)
    bundled = Path(__file__).parent / "Fonts"
    if bundled.exists() and any(bundled.glob("*.fnt")):
        return bundled

    # Fallback: user-installed fonts
    from ..paths import get_resources_dir as _get_resources_dir

    user_fonts = _get_resources_dir() / "Fonts"
    if user_fonts.exists():
        return user_fonts

    # Last resort: return bundled path even if empty (will fail gracefully)
    return bundled


def get_resources_dir() -> Path:
    """Get the base resources directory.

    For fonts, use get_fonts_dir() instead. This returns the user-level
    resources directory which contains animations and other downloaded content.

    Returns:
        Path to the resources directory.
    """
    from ..paths import get_resources_dir as _get_resources_dir

    return _get_resources_dir()
