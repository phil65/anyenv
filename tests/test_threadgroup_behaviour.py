"""ThreadGroup: result order, event loop, executor lifetime, errors."""

import asyncio
import threading
import time

import pytest

from anyenv.calling.threadgroup import ThreadGroup


def _sleep_then(value: str, delay: float) -> str:
    time.sleep(delay)
    return value


def test_results_in_spawn_order():
    """Results line up with spawn order, not completion order."""
    with ThreadGroup[str]() as tg:
        tg.spawn(_sleep_then, "slow", 0.1)
        tg.spawn(_sleep_then, "fast", 0)
    assert tg.results == ["slow", "fast"]


def test_exit_shuts_the_executor_down():
    """Leaving the group stops its worker threads."""
    with ThreadGroup[str]() as tg:
        tg.spawn(_sleep_then, "x", 0)
    assert tg.executor._shutdown  # noqa: SLF001


def test_error_waits_for_the_others():
    """On a failure the group still waits for its other threads."""
    finished = threading.Event()

    def slow() -> str:
        time.sleep(0.1)
        finished.set()
        return "done"

    def boom() -> str:
        raise ValueError("boom")

    def run() -> None:
        with ThreadGroup[str]() as tg:
            tg.spawn(slow)
            tg.spawn(boom)

    with pytest.raises(ValueError, match="boom"):
        run()
    assert finished.is_set()


async def test_async_exit_does_not_block_the_loop():
    """Waiting for the threads in __aexit__ leaves the event loop running."""
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    async with ThreadGroup[str]() as tg:
        tg.spawn(_sleep_then, "x", 0.2)
    task.cancel()
    assert tg.results == ["x"]
    assert ticks >= 5  # noqa: PLR2004
