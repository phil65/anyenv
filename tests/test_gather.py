"""Tests for anyenv.gather."""

import asyncio

import pytest

import anyenv


async def ok(value: int = 1, delay: float = 0) -> int:
    """Return value after a delay."""
    await asyncio.sleep(delay)
    return value


async def boom() -> int:
    """Fail."""
    raise ValueError("boom")


async def test_gather_keeps_order():
    """Results line up with the awaitables, not with completion order."""
    assert list(await anyenv.gather(ok(1, 0.02), ok(2))) == [1, 2]


async def test_gather_raises_the_error_itself():
    """Like asyncio.gather: the child's exception, not an ExceptionGroup."""
    with pytest.raises(ValueError, match="boom"):
        await anyenv.gather(ok(), boom())


async def test_gather_keeps_exception_groups_of_children():
    """A child that raises an ExceptionGroup itself keeps it whole."""

    async def group() -> int:
        raise ExceptionGroup("inner", [KeyError("k")])

    with pytest.raises(ExceptionGroup, match="inner"):
        await anyenv.gather(group())


async def test_gather_return_exceptions():
    """With return_exceptions, errors come back as results."""
    results = await anyenv.gather(ok(), boom(), return_exceptions=True)
    assert results[0] == 1
    assert isinstance(results[1], ValueError)


async def test_gather_return_exceptions_propagates_cancellation():
    """Cancelling the caller is not stored as a result."""
    task = asyncio.create_task(anyenv.gather(ok(1, 10), return_exceptions=True))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_call_and_gather_raises_the_error_itself():
    """call_and_gather inherits gather's behaviour."""
    with pytest.raises(ValueError, match="boom"):
        await anyenv.call_and_gather([ok, boom])
