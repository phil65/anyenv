"""Tests for async executor edge cases and error conditions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

import pytest

from anyenv.calling.async_executor import function_spawner, method_spawner


@dataclass
class SlowEvent:
    """Event that triggers slow processing."""

    delay: float
    payload: str


@dataclass
class FastEvent:
    """Event processed quickly."""

    data: int


@dataclass
class ExceptionEvent:
    """Event that causes handler exceptions."""

    should_fail: bool
    error_message: str


async def test_handler_exception_propagation():
    """Test that handler exceptions propagate as expected."""
    handler_calls: list[tuple[str, Any]] = []

    def fast_handler(event: FastEvent) -> None:
        handler_calls.append(("fast", event))

    @function_spawner
    async def error_prone_stream():
        """Stream that may trigger handler errors."""
        yield FastEvent(42)  # Should process before failure
        yield ExceptionEvent(False, "ok")  # Should work

    # Mock handlers
    working_handler = Mock()
    failing_handler = Mock(side_effect=ValueError("Handler failed"))

    # Connect handlers - one that works, one that fails
    error_prone_stream[ExceptionEvent].connect(working_handler)
    error_prone_stream[ExceptionEvent].connect(failing_handler)
    error_prone_stream[FastEvent].connect(fast_handler)

    # Process stream - should raise on first ExceptionEvent
    try:
        async for _ in error_prone_stream():
            pass
        msg = "Expected ValueError"
        raise AssertionError(msg)
    except ValueError as e:
        assert str(e) == "Handler failed"  # noqa: PT017

    # Working handler should be called once before failure
    assert working_handler.call_count == 1

    # Failing handler should be called once (and raise)
    assert failing_handler.call_count == 1

    # FastEvent handler should work
    fast_calls = [call for name, call in handler_calls if name == "fast"]
    assert len(fast_calls) == 1
    assert fast_calls[0].data == 42  # noqa: PLR2004


async def test_observer_mode_with_mixed_handler_speeds():
    """Test sequential vs parallel modes with handlers of different speeds."""
    handler_calls: list[tuple[str, Any]] = []

    def slow_handler(event: SlowEvent) -> None:
        import time

        time.sleep(event.delay)
        handler_calls.append(("slow", event))

    async def async_slow_handler(event: SlowEvent) -> None:
        await asyncio.sleep(event.delay)
        handler_calls.append(("async_slow", event))

    @function_spawner
    async def mixed_speed_events():
        """Generate events for speed testing."""
        for i in range(3):
            yield SlowEvent(0.1, f"slow_{i}")

    # Add both slow sync and async handlers
    mixed_speed_events[SlowEvent].connect(slow_handler)
    mixed_speed_events[SlowEvent].connect(async_slow_handler)

    # Test sequential mode
    mixed_speed_events.observer_mode = "sequential"
    start_time = asyncio.get_event_loop().time()

    async for _ in mixed_speed_events():
        pass

    sequential_duration = asyncio.get_event_loop().time() - start_time
    sequential_calls = len(handler_calls)

    # Clear for parallel test
    handler_calls.clear()

    # Test parallel mode
    mixed_speed_events.observer_mode = "parallel"
    start_time = asyncio.get_event_loop().time()

    async for _ in mixed_speed_events():
        pass

    parallel_duration = asyncio.get_event_loop().time() - start_time
    parallel_calls = len(handler_calls)

    # Both modes should call all handlers
    assert (
        sequential_calls == parallel_calls == 6  # noqa: PLR2004
    )  # 3 events * 2 handlers

    # Parallel should be faster (though timing tests are flaky)
    # We'll just verify it didn't take twice as long
    assert parallel_duration < sequential_duration * 1.5


async def test_dynamic_handler_modification():
    """Test adding/removing handlers while processing."""

    @function_spawner
    async def dynamic_stream():
        """Stream that allows dynamic handler changes."""
        for i in range(10):
            yield FastEvent(i)
            # Yield control to allow handler modifications
            await asyncio.sleep(0.001)

    handler1_calls = []
    handler2_calls = []

    def handler1(event: FastEvent):
        handler1_calls.append(event.data)

    def handler2(event: FastEvent):
        handler2_calls.append(event.data)

    async def modify_handlers(stream_coro):
        """Modify handlers while stream is running."""
        items = []
        i = 0
        async for _item in stream_coro:
            items.append(i)

            # Add second handler after 3 events
            if i == 2:  # noqa: PLR2004
                dynamic_stream[FastEvent].connect(handler2)

            # Remove first handler after 7 events
            elif i == 6:  # noqa: PLR2004
                dynamic_stream[FastEvent].disconnect(handler1)

            i += 1

        return items

    # Start with just handler1
    dynamic_stream[FastEvent].connect(handler1)

    # Process with dynamic modifications
    await modify_handlers(dynamic_stream())

    # handler1 should see events 0-6 (removed after event 6)
    assert handler1_calls == [0, 1, 2, 3, 4, 5, 6]

    # handler2 should see events 3-9 (added after event 2)
    assert handler2_calls == [3, 4, 5, 6, 7, 8, 9]


async def test_complex_event_filtering_combinations():
    """Test complex combinations of filters and handlers."""
    captured_events: list[tuple[str, Any]] = []

    def network_handler(event: Any):
        captured_events.append(("network", event))

    def error_handler(event: Any):
        captured_events.append(("error", event))

    def lambda_handler(event: Any):
        captured_events.append(("lambda", event))

    @function_spawner
    async def complex_stream():
        """Stream with multiple event types."""
        yield SlowEvent(0.1, "network_op")  # Should match lambda filter
        yield FastEvent(100)  # Should not match any filter
        yield ExceptionEvent(True, "network error")  # Should match error handler
        yield SlowEvent(0.05, "database_op")  # Should match lambda filter

    # Type-based filters
    complex_stream[ExceptionEvent].connect(error_handler)

    # Lambda-based filter for SlowEvent with specific payloads
    complex_stream.connect(
        lambda_handler,
        event_filter=lambda e: isinstance(e, SlowEvent) and "network" in e.payload,
    )

    # Process stream
    async for _ in complex_stream():
        pass

    # Verify filtering
    error_events = [e for tag, e in captured_events if tag == "error"]
    lambda_events = [e for tag, e in captured_events if tag == "lambda"]

    assert len(error_events) == 1
    assert error_events[0].error_message == "network error"

    assert len(lambda_events) == 1
    assert lambda_events[0].payload == "network_op"

    # FastEvent should not have been captured
    assert len(captured_events) == 2  # noqa: PLR2004


async def test_handler_performance_under_load():
    """Test system performance with many handlers and events."""

    @function_spawner
    async def high_volume_stream():
        """Generate many events."""
        for i in range(1000):
            if i % 10 == 0:
                yield SlowEvent(0.0, f"batch_{i}")
            else:
                yield FastEvent(i)

    # Create many handlers
    slow_handlers = [lambda e, idx=i: None for i in range(50)]
    fast_handlers = [lambda e, idx=i: None for i in range(50)]

    # Connect all handlers
    for handler in slow_handlers:
        high_volume_stream[SlowEvent].connect(handler)
    for handler in fast_handlers:
        high_volume_stream[FastEvent].connect(handler)

    start_time = asyncio.get_event_loop().time()

    # Process stream
    event_count = 0
    async for _ in high_volume_stream():
        event_count += 1

    duration = asyncio.get_event_loop().time() - start_time

    # Verify all events processed
    assert event_count == 1000  # noqa: PLR2004

    # Should complete in reasonable time (this is environment dependent)
    # Just verify it doesn't hang or take excessively long
    assert duration < 10.0  # noqa: PLR2004


async def test_nested_generator_event_handling():
    """Test event handling with nested async generators."""

    @function_spawner
    async def outer_generator():
        """Outer generator that yields from inner."""
        yield FastEvent(1)
        async for item in inner_generator():
            yield item
        yield FastEvent(999)

    async def inner_generator():
        """Inner generator."""
        for i in range(2, 5):
            yield SlowEvent(0.0, f"inner_{i}")

    captured = []

    def capture_all(event: Any):
        captured.append(event)

    # Connect handler to catch everything
    outer_generator.connect(capture_all)

    # Process
    async for _ in outer_generator():
        pass

    # Should have captured all events from both generators
    assert len(captured) == 5  # 2 FastEvent + 3 SlowEvent # noqa: PLR2004

    fast_events = [e for e in captured if isinstance(e, FastEvent)]
    slow_events = [e for e in captured if isinstance(e, SlowEvent)]

    assert len(fast_events) == 2  # noqa: PLR2004
    assert len(slow_events) == 3  # noqa: PLR2004
    assert fast_events[0].data == 1
    assert fast_events[1].data == 999  # noqa: PLR2004


async def test_isolated_observers_across_instances():
    """Test that observers are isolated per instance when decorating methods."""
    captured_events: list[tuple[str, Any]] = []

    def handler1(event: FastEvent) -> None:
        captured_events.append(("handler1", event))

    def handler2(event: FastEvent) -> None:
        captured_events.append(("handler2", event))

    class EventEmitter:
        def __init__(self, name: str):
            self.name = name

        @method_spawner
        async def emit_events(self, count: int):
            """Emit test events."""
            for i in range(count):
                yield FastEvent(i)

    # Create two instances
    emitter1 = EventEmitter("first")
    emitter2 = EventEmitter("second")

    # Connect handler1 to emitter1
    emitter1.emit_events.connect(handler1)

    # Connect handler2 to emitter2
    emitter2.emit_events.connect(handler2)

    # Process events from emitter1 - should trigger BOTH handlers due to sharing
    async for _ in emitter1.emit_events(2):
        pass

    # Should have captured events only from handler1 for emitter1's events
    handler1_events = [e for tag, e in captured_events if tag == "handler1"]
    handler2_events = [e for tag, e in captured_events if tag == "handler2"]

    # With isolated observers, only handler1 should fire for emitter1's events
    assert len(handler1_events) == 2  # noqa: PLR2004
    assert len(handler2_events) == 0  # handler2 should not see emitter1's events

    captured_events.clear()

    # Process events from emitter2 - again both handlers will fire
    async for _ in emitter2.emit_events(1):
        pass

    handler1_events = [e for tag, e in captured_events if tag == "handler1"]
    handler2_events = [e for tag, e in captured_events if tag == "handler2"]

    # With isolated observers, only handler2 should fire for emitter2's events
    assert len(handler1_events) == 0  # handler1 should not see emitter2's events
    assert len(handler2_events) == 1


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main(["-v", __file__])
