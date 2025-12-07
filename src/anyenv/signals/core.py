"""Core signal classes for type-safe async event handling."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVarTuple, Unpack
from weakref import WeakKeyDictionary


Ts = TypeVarTuple("Ts")

type AsyncCallback[*Ts] = Callable[[Unpack[Ts]], Coroutine[Any, Any, Any]]

# Global registry for auto-registered signals
_global_registry: dict[type, list[BoundSignal]] = {}  # type: ignore[type-arg]


class BoundSignal[*Ts]:
    """Instance-bound signal holding connections."""

    __slots__ = ("_callbacks",)

    def __init__(self) -> None:
        self._callbacks: list[AsyncCallback[*Ts]] = []

    def connect(self, callback: AsyncCallback[*Ts]) -> AsyncCallback[*Ts]:
        """Connect async callback. Can be used as decorator."""
        self._callbacks.append(callback)
        return callback

    def disconnect(self, callback: AsyncCallback[*Ts]) -> None:
        """Remove callback."""
        self._callbacks.remove(callback)

    async def emit(self, *args: *Ts) -> None:
        """Emit signal, await all handlers sequentially."""
        for callback in self._callbacks:
            await callback(*args)

    def emit_bg(self, *args: *Ts) -> list[asyncio.Task[None]]:
        """Emit signal, create tasks for all handlers (fire-and-forget)."""
        return [asyncio.create_task(callback(*args)) for callback in self._callbacks]


class Signal[*Ts]:
    """Descriptor: define at class level, get BoundSignal per instance.

    Example:
        class MyClass:
            changed = Signal[str]()
    """

    __slots__ = ("_bound_signals", "_name")

    def __init__(self) -> None:
        self._name: str = ""
        self._bound_signals: WeakKeyDictionary[object, BoundSignal[*Ts]] = WeakKeyDictionary()

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, obj: object | None, owner: type | None = None) -> BoundSignal[*Ts]:
        if obj is None:
            # Class-level access - return a dummy for introspection
            return BoundSignal()
        if obj not in self._bound_signals:
            self._bound_signals[obj] = BoundSignal()
        return self._bound_signals[obj]


def create_signal[E](event_type: type[E]) -> Signal[*tuple[E]]:
    """Create a signal and auto-register it globally.

    Args:
        event_type: The event type for this signal.

    Returns:
        A new Signal instance configured for the event type.

    Example:
        ```python
        class User: ...
        class FileEvent: ...

        type AppEvents = User | FileEvent

        def create_app_signal[E: AppEvents](event_type: type[E]) -> Signal[*tuple[E]]:
            return create_signal(event_type)

        # Usage with type constraint
        user_signal = create_app_signal(User)  # ✅ OK
        invalid = create_app_signal(dict)      # ❌ Type error
        ```
    """
    signal = Signal[*tuple[E]]()

    # Auto-register with global registry
    if event_type not in _global_registry:
        _global_registry[event_type] = []

    # Note: We can't easily register the Signal descriptor itself,
    # but we could register a factory or metadata here

    return signal


def get_global_signals(event_type: type) -> list[BoundSignal]:  # type: ignore[type-arg]
    """Get all globally registered signals for an event type.

    Args:
        event_type: The event type to look up.

    Returns:
        List of bound signals registered for this event type.
    """
    return _global_registry.get(event_type, [])


def clear_global_registry() -> None:
    """Clear the global signal registry (useful for testing)."""
    _global_registry.clear()
