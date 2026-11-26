"""``.sync()`` on async generators: bounded, closable, stops its producer."""

import gc
import threading
import time

from anyenv.calling.async_executor import function_spawner


def _counting_generator(produced: list[int], closed: threading.Event):
    @function_spawner
    async def count():
        try:
            i = 0
            while True:
                produced.append(i)
                yield i
                i += 1
        finally:
            closed.set()

    return count


def test_sync_iterates_lazily_and_completely():
    """A finite generator yields all its items, then stops."""

    @function_spawner
    async def three():
        for i in range(3):
            yield i

    assert list(three.sync()) == [0, 1, 2]


def test_sync_propagates_errors():
    """An error in the generator is raised by the consumer."""
    import pytest

    @function_spawner
    async def failing():
        yield 1
        raise ValueError("boom")

    it = failing.sync()
    assert next(it) == 1
    with pytest.raises(ValueError, match="boom"):
        next(it)


def test_queue_is_bounded():
    """The producer runs at most a bounded number of items ahead of the consumer."""
    produced: list[int] = []
    closed = threading.Event()
    it = _counting_generator(produced, closed).sync()
    assert next(it) == 0
    time.sleep(0.3)
    assert len(produced) < 100  # noqa: PLR2004
    it.close()


def test_close_stops_producer_and_closes_generator():
    """close() stops the producer thread and aclose()s the generator."""
    produced: list[int] = []
    closed = threading.Event()
    it = _counting_generator(produced, closed).sync()
    for i, item in enumerate(it):
        assert item == i
        if i == 2:  # noqa: PLR2004
            break
    it.close()
    assert closed.is_set()
    count = len(produced)
    time.sleep(0.1)
    assert len(produced) == count
    assert list(it) == []


def test_dropping_iterator_stops_producer():
    """An iterator dropped after an early break stops its producer too."""
    produced: list[int] = []
    closed = threading.Event()
    it = _counting_generator(produced, closed).sync()
    next(it)
    del it
    gc.collect()
    assert closed.wait(2)


def test_close_of_blocked_producer():
    """close() also stops a generator waiting on something that never happens."""
    import asyncio

    closed = threading.Event()

    @function_spawner
    async def stuck():
        try:
            yield 0
            await asyncio.Event().wait()
            yield 1
        finally:
            closed.set()

    it = stuck.sync()
    assert next(it) == 0
    it.close()
    assert closed.is_set()
