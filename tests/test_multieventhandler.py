"""Tests for MultiEventHandler debouncing."""

import asyncio

import pytest

from anyenv import MultiEventHandler


async def test_superseded_caller_gets_the_result_not_cancelled():
    """A call replaced by a later one resolves with that call's result."""
    calls: list[int] = []

    def handler(x: int) -> int:
        calls.append(x)
        return x * 10

    manager = MultiEventHandler([handler], debounce_delay=0.05)
    first = asyncio.create_task(manager(1))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(manager(2))
    assert await first == [20]
    assert await second == [20]
    assert calls == [2]  # debounced: only the last call ran
    assert not first.cancelled()


async def test_running_round_is_not_cancelled_by_a_new_call():
    """Once its delay is over, a round runs to completion for its callers."""
    started = asyncio.Event()

    async def handler(x: int) -> int:
        started.set()
        await asyncio.sleep(0.05)
        return x

    manager = MultiEventHandler([handler], debounce_delay=0.01)
    first = asyncio.create_task(manager(1))
    await started.wait()
    second = asyncio.create_task(manager(2))
    assert await first == [1]
    assert await second == [2]


async def test_cancelling_a_caller_leaves_the_others():
    """Cancelling one waiting caller doesn't cancel the round."""
    manager = MultiEventHandler([lambda x: x], debounce_delay=0.03)
    first = asyncio.create_task(manager(1))
    await asyncio.sleep(0)
    second = asyncio.create_task(manager(2))
    await asyncio.sleep(0)
    first.cancel()
    assert await second == [2]
    assert first.cancelled()


async def test_handler_error_reaches_every_caller():
    """A failing round raises its error in all of its callers."""

    def handler(x: int) -> int:
        raise ValueError(x)

    manager = MultiEventHandler([handler], debounce_delay=0.02)
    first = asyncio.create_task(manager(1))
    await asyncio.sleep(0)
    second = asyncio.create_task(manager(2))
    for task in (first, second):
        with pytest.raises(ValueError, match="2"):
            await task
