"""Type-safe async signals package.

A modern, type-safe event system built on Python's latest typing features.

Example using bounded TypeVar for type-safe signals:
    ```python
    from anyenv.signals import Signal

    # Define your event types
    class User: ...
    class FileEvent: ...
    class SystemEvent: ...

    # Create a bounded Signal subclass for your application
    class AppSignal[E: User | FileEvent | SystemEvent](Signal[E]):
        '''Application-specific signal constrained to allowed event types.'''
        pass

    # Use the bounded signal - type checker will enforce constraints
    class UserService:
        user_created = AppSignal[User]()      # ✅ OK
        file_saved = AppSignal[FileEvent]()   # ✅ OK
        invalid = AppSignal[dict]()           # ❌ Type error!
    ```
"""

from __future__ import annotations

from .core import BoundSignal, Signal, create_signal, get_global_signals, clear_global_registry

__all__ = [
    "BoundSignal",
    "Signal",
    "clear_global_registry",
    "create_signal",
    "get_global_signals",
]

__version__ = "0.1.0"
