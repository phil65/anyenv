"""Example usage of the signals package.

This module demonstrates core mechanisms of type-safe async signals.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from . import Signal, create_signal


# Example 1: Basic Signals
class Counter:
    """Simple counter with signals for state changes."""

    incremented = Signal[int]()
    reset = Signal[()]()

    def __init__(self, initial: int = 0) -> None:
        self._value = initial

    def increment(self) -> None:
        """Increment the counter and emit the incremented signal."""
        self._value += 1
        asyncio.create_task(self.incremented.emit(self._value))  # noqa: RUF006

    @property
    def value(self) -> int:
        """Return the current value of the counter."""
        return self._value


# Example 2: Type-Constrained Signals with Bounded TypeVar
@dataclass
class User:
    """User domain object."""

    id: int
    name: str
    email: str


@dataclass
class FileEvent:
    """File operation event."""

    path: Path
    operation: str
    size: int = 0


# Define allowed event types and create bounded Signal subclass
type AppEvents = User | FileEvent


class AppSignal[E: AppEvents](Signal[E]):
    """Application-specific signal constrained to allowed event types.

    Using a bounded TypeVar ensures that only User or FileEvent
    can be used as the signal's event type.
    """


class UserService:
    """Service handling user operations with type-safe events."""

    user_created = AppSignal[User]()
    user_updated = AppSignal[User]()

    async def create_user(self, name: str, email: str) -> User:
        """Create a new user and emit creation event."""
        user = User(id=123, name=name, email=email)
        await self.user_created.emit(user)
        return user


class FileService:
    """Service handling file operations with type-safe events."""

    file_created = AppSignal[FileEvent]()

    async def create_file(self, path: Path, content: str) -> None:
        """Create file and emit creation event."""
        event = FileEvent(path=path, operation="create", size=len(content))
        await self.file_created.emit(event)


# Cross-cutting concerns - listeners handling events from multiple services


class AuditLogger:
    """Audit logger that listens to user events."""

    def __init__(self, user_service: UserService) -> None:
        user_service.user_created.connect(self.on_user_created)
        user_service.user_updated.connect(self.on_user_updated)

    async def on_user_created(self, user: User) -> None:
        """Handle user creation events."""
        print(f"AUDIT: User created - {user.name}")

    async def on_user_updated(self, user: User) -> None:
        """Handle user update events."""
        print(f"AUDIT: User updated - {user.name}")


class NotificationService:
    """Sends notifications based on various events."""

    def __init__(self, user_service: UserService, file_service: FileService) -> None:
        user_service.user_created.connect(self.on_user_created)
        file_service.file_created.connect(self.on_file_created)

    async def on_user_created(self, user: User) -> None:
        """Handle user creation events."""
        print(f"NOTIFICATION: Welcome {user.name}!")

    async def on_file_created(self, event: FileEvent) -> None:
        """Handle file creation events."""
        print(f"NOTIFICATION: File created: {event.path} ({event.size} bytes)")


# Example 3: Factory Pattern with Auto-Registration


def create_app_signal[E: AppEvents](event_type: type[E]) -> Signal[*tuple[E]]:
    """Create an application signal with auto-registration.

    The bounded TypeVar ensures type safety.
    """
    return create_signal(event_type)


class UserServiceV2:
    """Alternative user service using factory pattern."""

    user_created = create_app_signal(User)

    async def create_user(self, name: str, email: str) -> User:
        """Create a new user and emit creation event."""
        user = User(id=123, name=name, email=email)
        await self.user_created.emit(user)
        return user


# Demonstrations


async def demonstrate_basic_signals() -> None:
    """Demonstrate basic signal usage."""
    print("=== Basic Signals ===")

    counter = Counter()

    @counter.incremented.connect
    async def on_increment(value: int) -> None:
        print(f"Counter: {value}")

    counter.increment()
    counter.increment()
    await asyncio.sleep(0.1)  # Let background tasks complete


async def demonstrate_type_constrained_signals() -> None:
    """Demonstrate type-constrained signals with cross-cutting concerns."""
    print("\n=== Type-Constrained Signals ===")

    user_service = UserService()
    file_service = FileService()

    # Wire up cross-cutting services
    AuditLogger(user_service)
    NotificationService(user_service, file_service)

    await user_service.create_user("Alice", "alice@example.com")
    await file_service.create_file(Path("/tmp/test.txt"), "Hello!")


async def demonstrate_factory_pattern() -> None:
    """Demonstrate factory pattern."""
    print("\n=== Factory Pattern ===")

    user_service = UserServiceV2()

    @user_service.user_created.connect
    async def on_user_created(user: User) -> None:
        print(f"Factory: User {user.name} created!")

    await user_service.create_user("Bob", "bob@example.com")


async def main() -> None:
    """Run all demonstrations."""
    await demonstrate_basic_signals()
    await demonstrate_type_constrained_signals()
    await demonstrate_factory_pattern()


if __name__ == "__main__":
    asyncio.run(main())
