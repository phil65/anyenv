"""Utilities for running async code in a synchronous context."""

from __future__ import annotations

import contextvars
import threading
from typing import TYPE_CHECKING, Any, Literal, overload

import anyio
from anyio import to_thread


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Sequence


def run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine synchronously.

    This function uses anyio to run a coroutine in a synchronous context.
    It attempts the following strategies in order:
    1. Tries to run using anyio's run function directly
    2. If that fails (already in an async context), runs in a new thread

    Context variables are properly propagated between threads in all cases.

    Example:
    ```python
    async def f(x: int) -> int:
        return x + 1

    result = run_sync(f(1))
    ```

    Args:
        coro: The coroutine to run synchronously

    Returns:
        The result of the coroutine
    """
    import anyio

    ctx = contextvars.copy_context()

    try:
        # Try to run directly with anyio
        return ctx.run(anyio.run, lambda: coro)
    except RuntimeError as e:
        # If we're already in an async context, run in a thread
        if "already running" in str(e):
            return run_sync_in_thread(coro)
        error_msg = str(e)
        msg = f"Failed to run coroutine: {error_msg}"
        raise RuntimeError(msg) from e


def run_sync_in_thread[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine synchronously in a new thread.

    This function creates a new thread to run the coroutine with anyio.
    Context variables are properly propagated between threads.
    This is useful when you need to run async code in a context where you can't use
    the current event loop (e.g., inside an async frame).

    Example:
    ```python
    async def f(x: int) -> int:
        return x + 1

    result = run_sync_in_thread(f(1))
    ```

    Args:
        coro: The coroutine to run synchronously

    Returns:
        The result of the coroutine
    """
    import anyio

    result: T | None = None
    error: BaseException | None = None
    done = threading.Event()
    ctx = contextvars.copy_context()

    def thread_target():
        nonlocal result, error
        try:
            result = ctx.run(anyio.run, lambda: coro)
        except BaseException as e:  # noqa: BLE001
            error = e
        finally:
            done.set()

    thread = threading.Thread(target=thread_target)
    thread.start()
    done.wait()

    if error is not None:
        raise error

    # We know result can't be None here if no exception was raised
    return result  # type: ignore


@overload
async def gather[T](
    *coros_or_futures: Awaitable[T],
    return_exceptions: Literal[True],
) -> Sequence[T | Exception]: ...


@overload
async def gather[T](
    *coros_or_futures: Awaitable[T],
    return_exceptions: Literal[False] = False,
) -> Sequence[T]: ...


async def gather[T](
    *coros_or_futures: Awaitable[T],
    return_exceptions: bool = False,
) -> Sequence[T | Exception]:
    """Run awaitables concurrently using anyio's task groups.

    Args:
        *coros_or_futures: Awaitables (coroutines or futures) to run concurrently
        return_exceptions: If True, exceptions are returned instead of raised

    Returns:
        A list of results in the same order as the input awaitables
    """
    results: list[Any] = [None] * len(coros_or_futures)

    async with anyio.create_task_group() as tg:
        for i, coro in enumerate(coros_or_futures):

            async def run_and_store(idx: int = i, awaitable: Awaitable[T] = coro):
                try:
                    results[idx] = await awaitable
                except Exception as exc:
                    if return_exceptions:
                        results[idx] = exc
                    else:
                        raise

            tg.start_soon(run_and_store)

    return results


async def run_in_thread[T](func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a function in a separate thread using anyio.

    Equivalent to asyncio.to_thread.
    """
    return await to_thread.run_sync(func, *args, **kwargs)
