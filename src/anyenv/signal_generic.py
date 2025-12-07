"""Type-safe async signals using TypeVarTuple generics.

Usage:
    class MyObject:
        value_changed = Signal[str]()
        pair_changed = Signal[str, int]()

    obj = MyObject()

    @obj.value_changed.connect
    async def on_change(value: str) -> None:
        print(f"Changed to {value}")

    await obj.value_changed.emit("hello")
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVarTuple, Unpack
from weakref import WeakKeyDictionary


Ts = TypeVarTuple("Ts")

type AsyncCallback[*Ts] = Callable[[Unpack[Ts]], Coroutine[Any, Any, Any]]


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


class SignalFactory:
    """Factory class that supports generic syntax Signal[Type]()."""

    __slots__ = ("_bus",)

    def __init__(self, bus: GlobalEventBus) -> None:
        self._bus = bus

    def __getitem__(self, types):
        """Support Signal[Type]() syntax."""
        if not isinstance(types, tuple):
            types = (types,)

        def create_signal() -> Signal:
            signal = Signal()
            # TODO: Auto-register signal with global listeners from self._bus
            return signal

        return create_signal


class GlobalEventBus:
    """Global event bus that provides Signal factory with auto-registration."""

    __slots__ = ("Signal", "_global_listeners", "_name")

    def __init__(self, name: str = "default") -> None:
        self._name = name
        self._global_listeners: dict[type, list[AsyncCallback]] = {}
        self.Signal = SignalFactory(self)

    def connect_global[*Ts](self, callback: AsyncCallback[*Ts]) -> AsyncCallback[*Ts]:
        """Connect a callback to receive ALL events of matching signature from this bus."""
        # TODO: Implementation for global cross-cutting listeners
        return callback


# Default global event bus instance
default_bus = GlobalEventBus("default")


if __name__ == "__main__":
    # Test regular signals
    class Counter:
        incremented = Signal[int]()
        reset = Signal[()]()
        pair_updated = Signal[str, int]()

    # Test global event bus
    class GlobalCounter:
        incremented = default_bus.Signal[int]()
        pair_updated = default_bus.Signal[str, int]()

    async def main() -> None:
        counter = Counter()

        @counter.incremented.connect
        async def on_increment(value: int) -> None:
            print(f"Counter incremented to {value}")

        @counter.pair_updated.connect
        async def on_pair(name: str, value: int) -> None:
            print(f"Pair updated: {name}={value}")

        # Test emit (awaited)
        print("Testing emit():")
        await counter.incremented.emit(42)
        await counter.pair_updated.emit("count", 100)

        # Test emit_bg (fire-and-forget)
        print("\nTesting emit_bg():")
        tasks = counter.incremented.emit_bg(99)
        await asyncio.gather(*tasks)

        # Test disconnect
        print("\nTesting disconnect:")
        counter.incremented.disconnect(on_increment)
        await counter.incremented.emit(123)  # Should print nothing
        print("(nothing printed = disconnect worked)")

        # Verify instance isolation
        print("\nTesting instance isolation:")
        counter2 = Counter()
        await counter2.incremented.emit(999)  # Should print nothing
        print("(nothing printed = isolation works)")

        # Test global event bus
        print("\nTesting global event bus:")
        global_counter = GlobalCounter()

        @global_counter.incremented.connect
        async def on_global_increment(value: int) -> None:
            print(f"Global counter: {value}")

        await global_counter.incremented.emit(777)

    asyncio.run(main())
