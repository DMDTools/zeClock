"""Centralized path resolution for zeClock.

All application paths are resolved here. Environment variables allow
overriding the default locations (useful for read-only root deployments
with a separate /data partition).

Environment variables:
    ZECLOCK_DATA_DIR: Base data directory (default: ~/.zeclock)
        Contains: lib/, resources/, plugins/, bin/
    ZECLOCK_CONFIG_DIR: Configuration directory (default: <data_dir>/config)
        Contains: zeclock.ini, plugins.yaml, dmdserver.ini
    ZECLOCK_RESOURCES_DIR: Resources directory (default: <data_dir>/resources)
        Contains: Fonts/, animations/
    ZECLOCK_LIB_DIR: Library directory (default: <data_dir>/lib)
        Contains: libzedmd.so, etc.
"""

import os
from pathlib import Path


def get_data_dir() -> Path:
    """Get the base zeClock data directory.

    Resolution:
        1. ZECLOCK_DATA_DIR environment variable
        2. ~/.zeclock (default)

    Returns:
        Path to the zeClock data directory.
    """
    env = os.environ.get("ZECLOCK_DATA_DIR")
    if env:
        return Path(env)
    return Path.home() / ".zeclock"


def get_config_dir() -> Path:
    """Get the zeClock configuration directory.

    Resolution:
        1. ZECLOCK_CONFIG_DIR environment variable
        2. <data_dir>/config (default)

    Returns:
        Path to the configuration directory.
    """
    env = os.environ.get("ZECLOCK_CONFIG_DIR")
    if env:
        return Path(env)
    return get_data_dir() / "config"


def get_lib_dir() -> Path:
    """Get the library directory (libzedmd, etc.).

    Resolution:
        1. ZECLOCK_LIB_DIR environment variable
        2. <data_dir>/lib (default)

    Returns:
        Path to the library directory.
    """
    env = os.environ.get("ZECLOCK_LIB_DIR")
    if env:
        return Path(env)
    return get_data_dir() / "lib"


def get_resources_dir() -> Path:
    """Get the resources directory (fonts, animations).

    Resolution:
        1. ZECLOCK_RESOURCES_DIR environment variable
        2. <data_dir>/resources (default)

    Returns:
        Path to the resources directory.
    """
    env = os.environ.get("ZECLOCK_RESOURCES_DIR")
    if env:
        return Path(env)
    return get_data_dir() / "resources"


def get_plugins_dir() -> Path:
    """Get the user plugins directory.

    Returns:
        Path to <data_dir>/plugins/
    """
    return get_data_dir() / "plugins"


def get_install_dir() -> Path:
    """Get the install directory (dmdserver binary).

    Returns:
        Path to <data_dir>/bin/
    """
    return get_data_dir() / "bin"
