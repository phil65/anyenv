"""Tests for anyenv.run_sync."""

from __future__ import annotations

import asyncio

import pytest

from anyenv import run_sync


def test_run_sync_returns_result():
    """Outside an event loop it runs the coroutine directly."""

    async def f(x: int) -> int:
        return x + 1

    assert run_sync(f(1)) == 2  # noqa: PLR2004


def test_run_sync_keeps_the_coroutines_own_runtime_error():
    """A RuntimeError from the coroutine is neither retried nor rewrapped."""
    calls = 0
    msg = "server already running on port 80"

    async def f() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match=rf"^{msg}$"):
        run_sync(f())
    assert calls == 1


async def test_run_sync_inside_event_loop_uses_a_thread():
    """Inside a running loop it runs the coroutine in another thread."""

    async def f() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    assert run_sync(f()) is not asyncio.get_running_loop()
