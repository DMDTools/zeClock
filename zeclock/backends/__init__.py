"""DMD display backends for zeClock.

This package exposes the backend ABC, the pure-Python DMDServerBackend, and the
factory function.  ZeDMDBackend is intentionally NOT exported at package level:
importing it triggers ctypes loading of libzedmd, which raises ImportError on
machines where the native library is absent.  Instead, ZeDMDBackend is imported
lazily inside ``factory.py`` so that the application can gracefully fall back to
DMDServerBackend when libzedmd is unavailable.
"""

from .base import DMDBackend
from .dmdserver import DMDServerBackend
from .factory import create_backend

__all__ = ["DMDBackend", "DMDServerBackend", "create_backend"]
