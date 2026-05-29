"""
Backward-compatible alias for DMDServerBackend.

This module is kept for backward compatibility. New code should import
from zeclock.backends.dmdserver directly.
"""

from zeclock.backends.dmdserver import DMDServerBackend as DMDServerClient

__all__ = ["DMDServerClient"]
