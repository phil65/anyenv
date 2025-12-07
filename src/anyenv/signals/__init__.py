"""Type-safe async signals package.

A modern, type-safe event system built on Python's latest typing features.
Provides both local signals and global event buses with union type constraints.

Example:
    # Basic signals
    class Counter:
        incremented = Signal[int]()

    # Global event bus with type constraints
    AllowedEvents = User | FileEvent | SystemEvent
    bus = GlobalEventBus[AllowedEvents]("app")

    class UserService:
        user_login = bus.Signal[User]()
"""

from __future__ import annotations

from .core import BoundSignal, Signal
from .bus import GlobalEventBus, SignalFactory, default_bus

__all__ = [
    "BoundSignal",
    "GlobalEventBus",
    "Signal",
    "SignalFactory",
    "default_bus",
]

__version__ = "0.1.0"
