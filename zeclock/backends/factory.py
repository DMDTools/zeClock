"""Backend factory for selecting and instantiating the appropriate DMD backend."""

import logging
import sys
from typing import Optional

from .base import DMDBackend

logger = logging.getLogger(__name__)

VALID_BACKENDS = ("auto", "zedmd", "dmdserver")


def create_backend(
    backend: str = "auto",
    wifi_addr: Optional[str] = None,
    device: Optional[str] = None,
    brightness: int = 10,
    dmdserver_host: str = "localhost",
    dmdserver_port: int = 6789,
    width: int = 128,
    height: int = 32,
) -> DMDBackend:
    """Create and return the appropriate DMD backend.

    Args:
        backend: Backend mode — "auto", "zedmd", or "dmdserver".
        wifi_addr: ZeDMD WiFi IP address.
        device: ZeDMD USB serial device path.
        brightness: Display brightness (0-15).
        dmdserver_host: TCP host for dmdserver backend.
        dmdserver_port: TCP port for dmdserver backend.
        width: Display width in pixels.
        height: Display height in pixels.

    Returns:
        An instantiated DMDBackend (not yet connected — caller calls connect()).

    Raises:
        SystemExit: If the requested backend cannot be initialized.
    """
    if backend not in VALID_BACKENDS:
        logger.error(
            "Invalid backend: '%s'. Valid options: %s",
            backend,
            ", ".join(VALID_BACKENDS),
        )
        sys.exit(1)

    if backend == "zedmd":
        return _create_zedmd(wifi_addr, device, brightness, width, height)
    elif backend == "dmdserver":
        return _create_dmdserver(dmdserver_host, dmdserver_port)
    else:
        # auto mode
        return _create_auto(
            wifi_addr, device, brightness, dmdserver_host, dmdserver_port, width, height
        )


def _create_zedmd(
    wifi_addr: Optional[str],
    device: Optional[str],
    brightness: int,
    width: int,
    height: int,
) -> DMDBackend:
    """Instantiate ZeDMDBackend exclusively. Exit on failure."""
    try:
        from .zedmd import ZeDMDBackend

        instance = ZeDMDBackend(
            wifi_addr=wifi_addr,
            device=device,
            brightness=brightness,
            width=width,
            height=height,
        )
        logger.info("Selected backend: zedmd")
        return instance
    except ImportError as e:
        logger.error("Cannot use zedmd backend: %s", e)
        sys.exit(1)


def _create_dmdserver(host: str, port: int) -> DMDBackend:
    """Instantiate DMDServerBackend exclusively. Exit on failure."""
    try:
        from .dmdserver import DMDServerBackend

        instance = DMDServerBackend(host=host, port=port)
        logger.info("Selected backend: dmdserver")
        return instance
    except Exception as e:
        logger.error("Cannot use dmdserver backend: %s", e)
        sys.exit(1)


def _create_auto(
    wifi_addr: Optional[str],
    device: Optional[str],
    brightness: int,
    dmdserver_host: str,
    dmdserver_port: int,
    width: int,
    height: int,
) -> DMDBackend:
    """Try ZeDMDBackend first, fall back to DMDServerBackend.

    In auto mode, attempt to instantiate ZeDMDBackend. If that fails
    (ImportError when libzedmd is not available), fall back to
    DMDServerBackend. If both fail, exit with an error listing both
    failure reasons.
    """
    zedmd_error: Optional[str] = None
    dmdserver_error: Optional[str] = None

    # Try ZeDMDBackend first
    try:
        from .zedmd import ZeDMDBackend

        instance = ZeDMDBackend(
            wifi_addr=wifi_addr,
            device=device,
            brightness=brightness,
            width=width,
            height=height,
        )
        logger.info("Selected backend: zedmd")
        return instance
    except ImportError as e:
        zedmd_error = str(e)
        logger.debug("ZeDMD backend unavailable: %s", e)

    # Fall back to DMDServerBackend
    try:
        from .dmdserver import DMDServerBackend

        fallback = DMDServerBackend(host=dmdserver_host, port=dmdserver_port)
        logger.info("Selected backend: dmdserver")
        return fallback
    except Exception as e:
        dmdserver_error = str(e)
        logger.debug("DMDServer backend unavailable: %s", e)

    # Both failed
    logger.error(
        "No backend available. ZeDMD: %s. DMDServer: %s.",
        zedmd_error,
        dmdserver_error,
    )
    sys.exit(1)
