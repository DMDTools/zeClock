"""Tests for the DMDBackend abstract base class."""

from typing import Tuple
from unittest.mock import MagicMock

import pytest
from PIL import Image

from zeclock.backends.base import DMDBackend


class TestABCEnforcement:
    """Test that DMDBackend cannot be instantiated directly."""

    def test_cannot_instantiate_abc_directly(self):
        """DMDBackend is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            DMDBackend()

    def test_subclass_missing_connect_raises_typeerror(self):
        """A subclass missing connect() cannot be instantiated."""

        class Incomplete(DMDBackend):
            @property
            def connected(self) -> bool:
                return False

            def send_frame(self, image, buffered=True, color=(255, 128, 0)):
                return True

            def disconnect(self):
                pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_missing_send_frame_raises_typeerror(self):
        """A subclass missing send_frame() cannot be instantiated."""

        class Incomplete(DMDBackend):
            @property
            def connected(self) -> bool:
                return False

            def connect(self):
                return True

            def disconnect(self):
                pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_missing_disconnect_raises_typeerror(self):
        """A subclass missing disconnect() cannot be instantiated."""

        class Incomplete(DMDBackend):
            @property
            def connected(self) -> bool:
                return False

            def connect(self):
                return True

            def send_frame(self, image, buffered=True, color=(255, 128, 0)):
                return True

        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_missing_connected_property_raises_typeerror(self):
        """A subclass missing the connected property cannot be instantiated."""

        class Incomplete(DMDBackend):
            def connect(self):
                return True

            def send_frame(self, image, buffered=True, color=(255, 128, 0)):
                return True

            def disconnect(self):
                pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_complete_subclass_can_be_instantiated(self):
        """A subclass implementing all abstract methods can be instantiated."""

        class Complete(DMDBackend):
            @property
            def connected(self) -> bool:
                return False

            def connect(self) -> bool:
                return True

            def send_frame(
                self,
                image: Image.Image,
                buffered: bool = True,
                color: Tuple[int, int, int] = (255, 128, 0),
            ) -> bool:
                return True

            def disconnect(self) -> None:
                pass

        instance = Complete()
        assert instance is not None


class TestContextManagerProtocol:
    """Test that __enter__ calls connect() and __exit__ calls disconnect()."""

    def _make_backend(self):
        """Create a concrete backend with mocked connect/disconnect."""

        class ConcreteBackend(DMDBackend):
            def __init__(self):
                self._connected = False
                self.connect_called = False
                self.disconnect_called = False

            @property
            def connected(self) -> bool:
                return self._connected

            def connect(self) -> bool:
                self.connect_called = True
                self._connected = True
                return True

            def send_frame(self, image, buffered=True, color=(255, 128, 0)):
                return True

            def disconnect(self) -> None:
                self.disconnect_called = True
                self._connected = False

        return ConcreteBackend()

    def test_enter_calls_connect_and_returns_self(self):
        """__enter__ should call connect() and return the instance."""
        backend = self._make_backend()
        result = backend.__enter__()
        assert backend.connect_called
        assert result is backend

    def test_exit_calls_disconnect(self):
        """__exit__ should call disconnect()."""
        backend = self._make_backend()
        backend.__enter__()
        backend.__exit__(None, None, None)
        assert backend.disconnect_called

    def test_context_manager_with_statement(self):
        """Using 'with' statement calls connect on entry and disconnect on exit."""
        backend = self._make_backend()
        with backend as b:
            assert b is backend
            assert backend.connect_called
            assert backend.connected
        assert backend.disconnect_called
        assert not backend.connected

    def test_exit_does_not_suppress_exceptions(self):
        """__exit__ should return None/False, not suppressing exceptions."""
        backend = self._make_backend()
        result = backend.__exit__(ValueError, ValueError("test"), None)
        # None or False means exceptions are NOT suppressed
        assert not result

    def test_exception_propagates_through_context_manager(self):
        """Exceptions raised inside 'with' block should propagate."""
        backend = self._make_backend()
        with pytest.raises(RuntimeError, match="test error"):
            with backend:
                raise RuntimeError("test error")
        # disconnect should still be called
        assert backend.disconnect_called
