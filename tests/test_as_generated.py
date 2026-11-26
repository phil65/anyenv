"""Tests for both as_generated implementations."""

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from anyenv import as_generated as queue_module
from anyenv.async_run import as_generated as merge


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable


def via_queue_module(iterables: list[Any], **kwargs: Any) -> AsyncIterator[Any]:
    """The queue-capable variant, called with iterables only."""
    return queue_module.as_generated(iterables, **kwargs)


IMPLEMENTATIONS = pytest.mark.parametrize("impl", [merge, via_queue_module])


async def values(*items: Any) -> AsyncIterator[Any]:
    """Yield the items, giving other tasks a turn in between."""
    for item in items:
        await asyncio.sleep(0)
        yield item


async def forever() -> AsyncIterator[int]:
    """Never yield."""
    await asyncio.Event().wait()
    yield 0


async def failing(*items: Any) -> AsyncIterator[Any]:
    """Yield the items, then fail."""
    async for item in values(*items):
        yield item
    raise ValueError("boom")


@IMPLEMENTATIONS
async def test_cancellation_propagates_to_consumer(impl: Callable[..., AsyncIterator[Any]]):
    """Cancelling the consuming task must cancel it, not end its loop normally."""
    reached_after_loop = False

    async def consume() -> None:
        nonlocal reached_after_loop
        async for _ in impl([forever()]):
            pass
        reached_after_loop = True

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not reached_after_loop
    assert task.cancelled()


@IMPLEMENTATIONS
async def test_none_values_are_kept(impl: Callable[..., AsyncIterator[Any]]):
    """None is a value like any other."""
    result = [v async for v in impl([values(1, None, 2, None, 3), values("a", "b", "c")])]
    assert sorted(result, key=repr) == sorted([1, None, 2, None, 3, "a", "b", "c"], key=repr)


@IMPLEMENTATIONS
async def test_error_of_last_source_is_raised(impl: Callable[..., AsyncIterator[Any]]):
    """An error is raised even when its source is the last one to finish."""
    seen: list[Any] = []

    async def consume() -> None:
        async for v in impl([failing(1, 2)]):
            seen.append(v)  # noqa: PERF401

    with pytest.raises(ValueError, match="boom"):
        await consume()
    assert seen == [1, 2]


@IMPLEMENTATIONS
async def test_error_yielded_with_return_exceptions(impl: Callable[..., AsyncIterator[Any]]):
    """With return_exceptions the error comes as a value and the rest goes on."""
    result = [v async for v in impl([failing(1), values(2, 3)], return_exceptions=True)]
    errors = [v for v in result if isinstance(v, ValueError)]
    assert len(errors) == 1
    assert sorted(v for v in result if not isinstance(v, ValueError)) == [1, 2, 3]


@IMPLEMENTATIONS
async def test_early_break_closes_sources(impl: Callable[..., AsyncIterator[Any]]):
    """Leaving the loop early stops the source tasks."""
    closed = asyncio.Event()

    async def endless() -> AsyncIterator[int]:
        try:
            i = 0
            while True:
                await asyncio.sleep(0)
                yield i
                i += 1
        finally:
            closed.set()

    gen = impl([endless()])
    async for v in gen:
        if v == 3:  # noqa: PLR2004
            break
    await gen.aclose()  # type: ignore[attr-defined]
    await asyncio.wait_for(closed.wait(), 1)


async def test_queues_end_at_none():
    """Queues still end at a None item."""
    queue: asyncio.Queue[int | None] = asyncio.Queue()
    for item in (1, 2, None):
        queue.put_nowait(item)
    result = [v async for v in queue_module.as_generated([values("a")], [queue])]
    assert sorted(result, key=repr) == sorted([1, 2, "a"], key=repr)
