"""Tests for async executor event filtering system."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from anyenv.calling.async_executor import function_spawner, method_spawner


@dataclass
class NetworkEvent:
    """Network event."""

    action: str
    target: str


@dataclass
class DatabaseEvent:
    """Database event."""

    table: str
    operation: str
    record_id: int


@dataclass
class ErrorEvent:
    """Error event."""

    message: str
    code: int


@dataclass
class CompleteEvent:
    """Completion event."""

    success: bool
    duration: float


async def test_single_event_type_filtering():
    """Test filtering for single event types."""
    captured_events: list[tuple[str, Any]] = []

    def network_handler(event: NetworkEvent) -> None:
        captured_events.append(("network", event))

    def database_handler(event: DatabaseEvent) -> None:
        captured_events.append(("database", event))

    def error_handler(event: ErrorEvent) -> None:
        captured_events.append(("error", event))

    @function_spawner
    async def complex_operation():
        """Operation that emits multiple event types."""
        yield NetworkEvent("connect", "api.example.com")
        yield DatabaseEvent("users", "insert", 123)
        yield ErrorEvent("timeout", 408)
        yield CompleteEvent(False, 1.5)

    # Connect type-specific handlers
    complex_operation[NetworkEvent].connect(network_handler)
    complex_operation[DatabaseEvent].connect(database_handler)
    complex_operation[ErrorEvent].connect(error_handler)

    # Execute and consume all events
    async for _ in complex_operation():
        pass

    # Check each handler only got its event type
    network_events = [e for tag, e in captured_events if tag == "network"]
    db_events = [e for tag, e in captured_events if tag == "database"]
    error_events = [e for tag, e in captured_events if tag == "error"]

    assert len(network_events) == 1
    assert network_events[0].action == "connect"

    assert len(db_events) == 1
    assert db_events[0].table == "users"
    assert db_events[0].record_id == 123  # noqa: PLR2004

    assert len(error_events) == 1
    assert error_events[0].code == 408  # noqa: PLR2004


async def test_union_event_filtering():
    """Test filtering for multiple event types with union syntax."""
    captured_events: list[tuple[str, Any]] = []

    def universal_handler(event: Any) -> None:
        captured_events.append(("universal", event))

    @function_spawner
    async def multi_stage_process():
        """Process with multiple stages and error handling."""
        yield NetworkEvent("start", "server")
        yield DatabaseEvent("logs", "insert", 1)
        yield ErrorEvent("connection lost", 500)
        yield DatabaseEvent("retries", "increment", 1)
        yield CompleteEvent(False, 2.1)

    # Connect union handler for database OR error events
    multi_stage_process[DatabaseEvent | ErrorEvent].connect(universal_handler)

    # Execute
    async for _ in multi_stage_process():
        pass

    # Should capture 3 events: 2 database + 1 error
    universal_events = [e for tag, e in captured_events if tag == "universal"]
    assert len(universal_events) == 3  # noqa: PLR2004

    # Check event types
    event_types = [type(event).__name__ for event in universal_events]
    assert event_types.count("DatabaseEvent") == 2  # noqa: PLR2004
    assert event_types.count("ErrorEvent") == 1


async def test_lambda_filter_vs_type_filter():
    """Test lambda filtering vs type-based filtering performance and behavior."""

    @function_spawner
    async def data_processor():
        """Generate various events."""
        for i in range(100):
            if i % 3 == 0:
                yield ErrorEvent(f"error_{i}", i)
            else:
                yield CompleteEvent(i % 2 == 0, float(i))

    type_filtered_events = []
    lambda_filtered_events = []

    def type_handler(event: ErrorEvent):
        type_filtered_events.append(event)

    def lambda_handler(event: Any):
        lambda_filtered_events.append(event)

    # Type-based filtering
    data_processor[ErrorEvent].connect(type_handler)

    # Lambda-based filtering (should be equivalent)
    data_processor.connect(
        lambda_handler, event_filter=lambda e: isinstance(e, ErrorEvent)
    )

    # Execute
    async for _ in data_processor():
        pass

    # Both should capture same events (every 3rd iteration)
    assert len(type_filtered_events) == len(lambda_filtered_events)
    assert len(type_filtered_events) == 34  # 100//3 + 1  # noqa: PLR2004

    # Verify they're actually ErrorEvents
    assert all(isinstance(e, ErrorEvent) for e in type_filtered_events)
    assert all(isinstance(e, ErrorEvent) for e in lambda_filtered_events)


async def test_filtered_handler_lifecycle():
    """Test connection/disconnection of filtered handlers."""
    captured_events: list[tuple[str, Any]] = []

    def network_handler(event: NetworkEvent) -> None:
        captured_events.append(("network", event))

    def database_handler(event: DatabaseEvent) -> None:
        captured_events.append(("database", event))

    @function_spawner
    async def event_source():
        """Simple event source."""
        yield NetworkEvent("test", "localhost")
        yield DatabaseEvent("test", "select", 1)

    # Connect and verify - create new instance to avoid cross-test pollution
    connection = event_source[NetworkEvent]
    connection.connect(network_handler)

    # Execute - should capture network event
    async for _ in event_source():
        pass
    assert len(captured_events) == 1

    # Disconnect and verify cleanup
    connection.disconnect(network_handler)
    captured_events.clear()

    # Create new function instance to avoid any state issues
    @function_spawner
    async def clean_event_source():
        """Clean event source."""
        yield NetworkEvent("test2", "localhost")
        yield DatabaseEvent("test2", "select", 2)

    # Execute again - should capture nothing
    async for _ in clean_event_source():
        pass
    assert len(captured_events) == 0

    # Reconnect different type to clean source
    clean_event_source[DatabaseEvent].connect(database_handler)

    # Execute - should only capture database event
    async for _ in clean_event_source():
        pass
    assert len(captured_events) == 1
    assert captured_events[0][0] == "database"


async def test_bound_method_event_filtering():
    """Test event filtering works with bound methods."""
    captured_events: list[tuple[str, Any]] = []

    def error_handler(event: ErrorEvent) -> None:
        captured_events.append(("error", event))

    def database_handler(event: DatabaseEvent) -> None:
        captured_events.append(("database", event))

    class EventEmitter:
        def __init__(self, name: str):
            self.name = name

        @method_spawner
        async def process_batch(self, items: list[str]):
            """Process items and emit events."""
            for i, item in enumerate(items):
                if "error" in item:
                    yield ErrorEvent(f"Bad item: {item}", 400)
                else:
                    yield DatabaseEvent("items", "insert", i)

    emitter1 = EventEmitter("worker1")
    emitter2 = EventEmitter("worker2")

    # Clear any existing state
    captured_events.clear()

    # Connect error handler only to emitter1
    emitter1.process_batch[ErrorEvent].connect(error_handler)

    # Process batch with emitter1 - should only capture error
    async for _ in emitter1.process_batch(["good1", "error_item", "good2"]):
        pass

    error_events = [e for tag, e in captured_events if tag == "error"]
    assert len(error_events) == 1
    assert "error_item" in error_events[0].message

    # Clear and test emitter2 separately
    captured_events.clear()

    # Connect database handler only to emitter2
    emitter2.process_batch[DatabaseEvent].connect(database_handler)

    # Process batch with emitter2 - should only capture database events
    async for _ in emitter2.process_batch(["item1", "item2", "item3"]):
        pass

    db_events = [e for tag, e in captured_events if tag == "database"]
    assert len(db_events) == 3  # 3 items # noqa: PLR2004

    # Verify isolation - no errors should be captured by emitter2
    error_events = [e for tag, e in captured_events if tag == "error"]
    assert len(error_events) == 0


async def test_concurrent_event_streams():
    """Test multiple concurrent event streams with filtering."""
    handler_calls: list[tuple[str, Any]] = []

    async def async_slow_handler(event: Any) -> None:
        await asyncio.sleep(0.01)
        handler_calls.append(("async_slow", event))

    def fast_handler(event: Any) -> None:
        handler_calls.append(("fast", event))

    @function_spawner
    async def event_stream(stream_id: int, count: int):
        """Generate events with stream identifier."""
        for i in range(count):
            if i % 2 == 0:
                yield DatabaseEvent("slow_table", "insert", stream_id * 100 + i)
            else:
                yield NetworkEvent("fast_action", f"stream_{stream_id}")

    # Connect handlers
    event_stream[DatabaseEvent].connect(async_slow_handler)
    event_stream[NetworkEvent].connect(fast_handler)

    async def consume_stream(stream):
        async for _ in stream:
            pass

    # Run multiple streams concurrently
    await asyncio.gather(
        consume_stream(event_stream(1, 5)),
        consume_stream(event_stream(2, 5)),
        consume_stream(event_stream(3, 5)),
    )

    # Should have handled all events from all streams
    slow_calls = [call for name, call in handler_calls if name == "async_slow"]
    fast_calls = [call for name, call in handler_calls if name == "fast"]
    # 3 streams * 3 slow events each (0, 2, 4)
    assert len(slow_calls) == 9  # noqa: PLR2004
    assert len(fast_calls) == 6  # 3 streams * 2 fast events each (1, 3)  # noqa: PLR2004


async def test_memory_cleanup_on_disconnect():
    """Test that filtered handlers are properly cleaned up."""

    @function_spawner
    async def cleanup_test():
        """Simple event source for cleanup testing."""
        yield NetworkEvent("test", "localhost")

    # Create many handlers and connect them
    handlers = [lambda e, i=i: None for i in range(100)]

    for handler in handlers:
        cleanup_test[NetworkEvent].connect(handler)

    # Verify they're all tracked
    assert len(cleanup_test._filtered_handlers[(NetworkEvent,)]) == 100  # noqa: PLR2004, SLF001

    # Disconnect them all
    for handler in handlers:
        cleanup_test[NetworkEvent].disconnect(handler)

    # Verify cleanup - the key should be removed entirely
    assert (NetworkEvent,) not in cleanup_test._filtered_handlers  # noqa: SLF001

    # Verify no memory leaks in observer system
    assert cleanup_test.observer_count == 0


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main(["-v", __file__])
