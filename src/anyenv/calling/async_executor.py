"""Decorator to add sync() method to async functions."""

from __future__ import annotations

import asyncio
import concurrent.futures
from functools import wraps
import inspect
from typing import TYPE_CHECKING, Any, Concatenate
import warnings


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class AsyncExecutor[**P, T]:
    """Wrapper that provides both async __call__ and sync() methods."""

    def __init__(self, func: Callable[..., Awaitable[T]], *, is_bound: bool) -> None:
        self._func = func
        self._instance: Any = None
        self._is_bound = is_bound
        # Copy function metadata
        wraps(func)(self)

    def __get__(self, instance: Any, owner: type | None = None) -> AsyncExecutor[P, T]:
        """Descriptor protocol for method binding."""
        if instance is None:
            return self
        # Always create bound wrapper to track instance
        bound = type(self)(self._func, is_bound=self._is_bound)
        bound._instance = instance  # noqa: SLF001
        return bound

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Async call - normal behavior."""
        if self._instance is not None and self._is_bound:
            # We're bound to an instance, prepend it to args
            return await self._func(self._instance, *args, **kwargs)
        return await self._func(*args, **kwargs)

    def sync(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Synchronous version using asyncio.run or thread pool."""
        coro = self(*args, **kwargs)

        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(coro)
        else:
            # We're in an async context, fall back to thread pool
            warnings.warn(
                "Calling .sync() from async context - using thread pool. "
                "Consider using 'await' instead for better performance.",
                UserWarning,
                stacklevel=2,
            )
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()

    def task(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
        """Create a Task for concurrent execution."""
        return asyncio.create_task(self(*args, **kwargs))

    def submit(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
        """Fire-and-forget execution, returns Task but doesn't need to be awaited."""
        task = self.task(*args, **kwargs)
        # Suppress task result retrieval warning
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return task

    async def timeout(self, timeout_sec: float, *args: P.args, **kwargs: P.kwargs) -> T:
        """Call with timeout."""
        return await asyncio.wait_for(self(*args, **kwargs), timeout_sec)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped function."""
        return getattr(self._func, name)


def method_spawner[**P, T](
    func: Callable[Concatenate[Any, P], Awaitable[T]],
) -> AsyncExecutor[P, T]:
    """Decorator for async methods.

    Usage:
        class MyClass:
            @method_spawner
            async def my_method(self, x: int) -> str:
                return str(x)

        # Usage:
        obj = MyClass()
        result = await obj.my_method(42)           # Async
        result = obj.my_method.sync(42)            # Sync
        task = obj.my_method.task(42)              # Task
        obj.my_method.submit(42)                   # Fire-and-forget
        result = await obj.my_method.timeout(5.0, 42)  # With timeout
    """
    if not inspect.iscoroutinefunction(func):
        msg = f"@method_spawner can only be applied to async methods, got {func}"
        raise TypeError(msg)
    return AsyncExecutor(func, is_bound=True)


def function_spawner[**P, T](
    func: Callable[P, Awaitable[T]],
) -> AsyncExecutor[P, T]:
    """Decorator for standalone async functions.

    Usage:
        @async_executor_function
        async def my_func(x: int) -> str:
            return str(x)

        # Usage:
        result = await my_func(42)           # Async
        result = my_func.sync(42)            # Sync
        task = my_func.task(42)              # Task
        my_func.submit(42)                   # Fire-and-forget
        result = await my_func.timeout(5.0, 42)  # With timeout
    """
    if not inspect.iscoroutinefunction(func):
        msg = f"@function_spawner can only be applied to async functions, got {func}"
        raise TypeError(msg)
    return AsyncExecutor(func, is_bound=False)
