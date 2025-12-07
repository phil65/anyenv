"""Example usage of the signals package.

This module demonstrates various ways to use the type-safe async signals.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from . import GlobalEventBus, Signal


# Example 1: Basic Signals
class Counter:
    """Simple counter with signals for state changes."""

    incremented = Signal[int]()
    reset = Signal[()]()
    pair_updated = Signal[str, int]()

    def __init__(self, initial: int = 0) -> None:
        self._value = initial

    def increment(self) -> None:
        """Increment the counter and emit the incremented signal."""
        self._value += 1
        asyncio.create_task(self.incremented.emit(self._value))  # noqa: RUF006

    def reset_counter(self) -> None:
        """Reset the counter to zero."""
        self._value = 0
        asyncio.create_task(self.reset.emit())  # noqa: RUF006

    @property
    def value(self) -> int:
        """Return the current value of the counter."""
        return self._value


# Example 2: Global Event Bus with Type Constraints


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


@dataclass
class SystemEvent:
    """System-level event."""

    level: str
    message: str
    timestamp: float


# Define allowed event types for our application
AppEvents = User | FileEvent | SystemEvent

# Create type-constrained event bus
app_bus = GlobalEventBus[AppEvents]("application")


class UserService:
    """Service handling user operations with type-safe events."""

    user_created = app_bus.Signal[User]()
    user_updated = app_bus.Signal[User]()
    user_deleted = app_bus.Signal[User]()

    async def create_user(self, name: str, email: str) -> User:
        """Create a new user and emit creation event."""
        # In real app, this would save to database
        user = User(id=123, name=name, email=email)
        await self.user_created.emit(user)
        return user

    async def update_user(self, user: User) -> None:
        """Update user and emit update event."""
        # In real app, this would update database
        await self.user_updated.emit(user)

    async def delete_user(self, user: User) -> None:
        """Delete user and emit deletion event."""
        # In real app, this would delete from database
        await self.user_deleted.emit(user)


class FileService:
    """Service handling file operations with type-safe events."""

    file_created = app_bus.Signal[FileEvent]()
    file_modified = app_bus.Signal[FileEvent]()
    file_deleted = app_bus.Signal[FileEvent]()

    async def create_file(self, path: Path, content: str) -> None:
        """Create file and emit creation event."""
        # In real app, this would write to filesystem
        event = FileEvent(path=path, operation="create", size=len(content))
        await self.file_created.emit(event)

    async def modify_file(self, path: Path, new_content: str) -> None:
        """Modify file and emit modification event."""
        # In real app, this would modify filesystem
        event = FileEvent(path=path, operation="modify", size=len(new_content))
        await self.file_modified.emit(event)


class SystemService:
    """Service handling system events."""

    error_occurred = app_bus.Signal[SystemEvent]()
    info_logged = app_bus.Signal[SystemEvent]()

    async def log_error(self, message: str) -> None:
        """Log system error."""
        import time

        event = SystemEvent(level="ERROR", message=message, timestamp=time.time())
        await self.error_occurred.emit(event)

    async def log_info(self, message: str) -> None:
        """Log system info."""
        import time

        event = SystemEvent(level="INFO", message=message, timestamp=time.time())
        await self.info_logged.emit(event)


# Cross-cutting concerns - listeners that handle events from multiple services


class AuditLogger:
    """Audit logger that listens to all user events."""

    def __init__(self, user_service: UserService) -> None:
        user_service.user_created.connect(self.on_user_created)
        user_service.user_updated.connect(self.on_user_updated)
        user_service.user_deleted.connect(self.on_user_deleted)

    async def on_user_created(self, user: User) -> None:
        """Handle user creation events."""
        print(f"AUDIT: User created - ID: {user.id}, Name: {user.name}")

    async def on_user_updated(self, user: User) -> None:
        """Handle user update events."""
        print(f"AUDIT: User updated - ID: {user.id}, Name: {user.name}")

    async def on_user_deleted(self, user: User) -> None:
        """Handle user deletion events."""
        print(f"AUDIT: User deleted - ID: {user.id}, Name: {user.name}")


class NotificationService:
    """Sends notifications based on various events."""

    def __init__(self, user_service: UserService, file_service: FileService) -> None:
        user_service.user_created.connect(self.on_user_created)
        file_service.file_created.connect(self.on_file_created)

    async def on_user_created(self, user: User) -> None:
        """Handle user creation events."""
        print(f"NOTIFICATION: Welcome {user.name}! Check your email at {user.email}")

    async def on_file_created(self, event: FileEvent) -> None:
        """Handle file creation events."""
        print(f"NOTIFICATION: New file created: {event.path} ({event.size} bytes)")


class MetricsCollector:
    """Collects metrics from all services."""

    def __init__(
        self, user_service: UserService, file_service: FileService, system_service: SystemService
    ) -> None:
        # User metrics
        user_service.user_created.connect(self.on_user_created)
        user_service.user_deleted.connect(self.on_user_deleted)

        # File metrics
        file_service.file_created.connect(self.on_file_created)
        file_service.file_modified.connect(self.on_file_modified)

        # System metrics
        system_service.error_occurred.connect(self.on_error)

    async def on_user_created(self, user: User) -> None:
        """Handle user creation events."""
        print("METRICS: user_created_total++")

    async def on_user_deleted(self, user: User) -> None:
        """Handle user deletion events."""
        print("METRICS: user_deleted_total++")

    async def on_file_created(self, event: FileEvent) -> None:
        """Handle file creation events."""
        print(f"METRICS: file_created_total++, bytes_written+={event.size}")

    async def on_file_modified(self, event: FileEvent) -> None:
        """Handle file modification events."""
        print(f"METRICS: file_modified_total++, bytes_written+={event.size}")

    async def on_error(self, event: SystemEvent) -> None:
        """Handle error events."""
        print(f"METRICS: error_total++ (level: {event.level})")


# Example with invalid usage (these would cause type errors):
# class InvalidService:
#     # These should cause type errors when type-checked:
#     invalid_event = app_bus.Signal[dict]()  # dict not in AppEvents union
#     str_event = app_bus.Signal[str]()       # str not in AppEvents union


async def demonstrate_basic_signals() -> None:
    """Demonstrate basic signal usage."""
    print("=== Basic Signals Demo ===")

    counter = Counter()

    @counter.incremented.connect
    async def on_increment(value: int) -> None:
        print(f"Counter incremented to: {value}")

    @counter.reset.connect
    async def on_reset() -> None:
        print("Counter was reset")

    @counter.pair_updated.connect
    async def on_pair_update(name: str, value: int) -> None:
        print(f"Pair updated: {name} = {value}")

    # Test the counter
    counter.increment()  # Fires task in background
    counter.increment()
    await counter.pair_updated.emit("test", 42)  # Direct emit
    counter.reset_counter()

    # Give background tasks time to complete
    await asyncio.sleep(0.1)


async def demonstrate_global_event_bus() -> None:
    """Demonstrate global event bus with cross-cutting concerns."""
    print("\n=== Global Event Bus Demo ===")

    # Create services
    user_service = UserService()
    file_service = FileService()
    system_service = SystemService()

    # Create cross-cutting services
    AuditLogger(user_service)
    NotificationService(user_service, file_service)
    MetricsCollector(user_service, file_service, system_service)

    # Perform some operations
    print("\n--- Creating user ---")
    user = await user_service.create_user("Alice", "alice@example.com")

    print("\n--- Creating file ---")
    await file_service.create_file(Path("/tmp/test.txt"), "Hello, World!")

    print("\n--- Updating user ---")
    user.name = "Alice Smith"
    await user_service.update_user(user)

    print("\n--- Logging error ---")
    await system_service.log_error("Something went wrong!")

    print("\n--- Deleting user ---")
    await user_service.delete_user(user)


async def demonstrate_emit_modes() -> None:
    """Demonstrate different emission modes."""
    print("\n=== Emit Modes Demo ===")

    counter = Counter()

    @counter.incremented.connect
    async def slow_handler(value: int) -> None:
        await asyncio.sleep(0.1)  # Simulate slow work
        print(f"Slow handler processed: {value}")

    @counter.incremented.connect
    async def fast_handler(value: int) -> None:
        print(f"Fast handler processed: {value}")

    print("Sequential emit (await all handlers):")
    await counter.incremented.emit(1)

    print("\nBackground emit (fire-and-forget):")
    tasks = counter.incremented.emit_bg(2)
    print("Tasks created immediately, handlers running in background")

    # Wait for background tasks
    await asyncio.gather(*tasks)
    print("Background tasks completed")


async def main() -> None:
    """Run all demonstrations."""
    await demonstrate_basic_signals()
    await demonstrate_global_event_bus()
    await demonstrate_emit_modes()


if __name__ == "__main__":
    asyncio.run(main())
