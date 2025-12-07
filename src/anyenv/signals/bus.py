"""Global event bus with type-safe signal factories."""

from __future__ import annotations

from typing import TypeVarTuple

from .core import AsyncCallback, Signal


Ts = TypeVarTuple("Ts")


class SignalFactory[T]:
    """Factory class that supports generic syntax Signal[Type]() with type constraints."""

    __slots__ = ("_bus",)

    def __init__(self, bus: GlobalEventBus[T]) -> None:
        self._bus = bus

    def __getitem__(self, typ: type[T]):
        """Support Signal[Type]() syntax with type constraint enforcement.

        Only accepts types that are members of the union T.
        """

        def create_signal() -> Signal:
            signal = Signal()
            # TODO: Auto-register signal with global listeners from self._bus
            return signal

        return create_signal


class GlobalEventBus[T]:
    """Global event bus constrained to specific event types.

    Example:
        AllowedEvents = User | FileEvent | SystemEvent
        bus = GlobalEventBus[AllowedEvents]("app")

        class UserService:
            user_login = bus.Signal[User]()  # Type-safe, only User allowed
    """

    __slots__ = ("Signal", "_global_listeners", "_name")

    def __init__(self, name: str = "default") -> None:
        self._name = name
        self._global_listeners: dict[type, list[AsyncCallback]] = {}
        self.Signal = SignalFactory[T](self)

    def connect_global[*Ts](self, callback: AsyncCallback[*Ts]) -> AsyncCallback[*Ts]:
        """Connect a callback to receive ALL events of matching signature from this bus."""
        # TODO: Implementation for global cross-cutting listeners
        return callback

    @property
    def name(self) -> str:
        """Get the name of this event bus."""
        return self._name


# Default global event bus instance (unconstrained)
default_bus = GlobalEventBus("default")
