"""Decorator to add sync() method to async functions."""

from __future__ import annotations

import asyncio
import concurrent.futures
from functools import wraps
import inspect
import queue
import threading
from typing import TYPE_CHECKING, Any, Concatenate, overload
import warnings


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator


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


class AsyncIteratorExecutor[**P, T]:
    """Wrapper that provides both async __call__ and sync() methods for async gens."""

    def __init__(self, func: Callable[..., AsyncIterator[T]], *, is_bound: bool) -> None:
        self._func = func
        self._instance: Any = None
        self._is_bound = is_bound
        # Copy function metadata
        wraps(func)(self)

    def __get__(
        self, instance: Any, owner: type | None = None
    ) -> AsyncIteratorExecutor[P, T]:
        """Descriptor protocol for method binding."""
        if instance is None:
            return self
        # Always create bound wrapper to track instance
        bound = type(self)(self._func, is_bound=self._is_bound)
        bound._instance = instance  # noqa: SLF001
        return bound

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
        """Return the async iterator directly."""
        if self._instance is not None and self._is_bound:
            # We're bound to an instance, prepend it to args
            return self._func(self._instance, *args, **kwargs)
        return self._func(*args, **kwargs)

    def sync(self, *args: P.args, **kwargs: P.kwargs) -> Iterator[T]:
        """Synchronous version that returns a truly lazy iterator."""

        class LazyAsyncIterator:
            def __init__(self, async_iter_func):
                self.async_iter_func = async_iter_func
                self.q: queue.Queue[T | Exception | object] = queue.Queue()
                self.thread = None
                self.started = False
                self.sentinel = object()  # Unique sentinel for end

            def _run_async(self):
                async def collect():
                    try:
                        async for item in self.async_iter_func():
                            self.q.put(item)
                    except Exception as e:  # noqa: BLE001
                        self.q.put(e)
                    finally:
                        self.q.put(self.sentinel)

                try:
                    # Check if we're already in an async context
                    asyncio.get_running_loop()
                    # In async context, run in thread pool
                    warnings.warn(
                        "Calling .sync() from async context - using thread pool. "
                        "Consider using 'async for' instead for better performance.",
                        UserWarning,
                        stacklevel=3,
                    )
                    asyncio.run(collect())
                except RuntimeError:
                    # No running loop, safe to use asyncio.run
                    asyncio.run(collect())

            def __iter__(self):
                return self

            def __next__(self):
                if not self.started:
                    self.thread = threading.Thread(target=self._run_async, daemon=True)
                    self.thread.start()
                    self.started = True

                item = self.q.get()
                if item is self.sentinel:
                    raise StopIteration
                if isinstance(item, Exception):
                    raise item
                return item

        return LazyAsyncIterator(lambda: self(*args, **kwargs))

    def task(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[list[T]]:
        """Create a Task that collects all values into a list."""

        async def _collect():
            return [item async for item in self(*args, **kwargs)]

        return asyncio.create_task(_collect())

    def submit(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[list[T]]:
        """Fire-and-forget execution that collects all values, returns Task."""
        task = self.task(*args, **kwargs)
        # Suppress task result retrieval warning
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return task

    async def timeout(
        self, timeout_sec: float, *args: P.args, **kwargs: P.kwargs
    ) -> list[T]:
        """Collect all values with timeout."""

        async def _collect():
            return [item async for item in self(*args, **kwargs)]

        return await asyncio.wait_for(_collect(), timeout_sec)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped function."""
        return getattr(self._func, name)


@overload
def method_spawner[**P, T](
    func: Callable[Concatenate[Any, P], Awaitable[T]],
) -> AsyncExecutor[P, T]: ...


@overload
def method_spawner[**P, T](
    func: Callable[Concatenate[Any, P], AsyncIterator[T]],
) -> AsyncIteratorExecutor[P, T]: ...


def method_spawner[**P, T](func) -> AsyncExecutor[P, T] | AsyncIteratorExecutor[P, T]:
    """Decorator for async methods and async generator methods.

    Usage:
        class MyClass:
            @method_spawner
            async def my_method(self, x: int) -> str:
                return str(x)

            @method_spawner
            async def my_generator(self, x: int):
                for i in range(x):
                    yield i

        # Usage:
        obj = MyClass()
        result = obj.my_method.sync(42)            # Sync
        for item in obj.my_generator.sync(3):     #  iteration
            print(item)
    """
    if inspect.iscoroutinefunction(func):
        return AsyncExecutor(func, is_bound=True)
    if inspect.isasyncgenfunction(func):
        return AsyncIteratorExecutor(func, is_bound=True)
    msg = f"@method_spawner must applied to async methods or async generators, got {func}"
    raise TypeError(msg)


@overload
def function_spawner[**P, T](
    func: Callable[P, Awaitable[T]],
) -> AsyncExecutor[P, T]: ...


@overload
def function_spawner[**P, T](
    func: Callable[P, AsyncIterator[T]],
) -> AsyncIteratorExecutor[P, T]: ...


def function_spawner[**P, T](func) -> AsyncExecutor[P, T] | AsyncIteratorExecutor[P, T]:
    """Decorator for standalone async functions and async generators.

    Usage:
        @function_spawner
        async def my_func(x: int) -> str:
            return str(x)

        @function_spawner
        async def my_generator(x: int):
            for i in range(x):
                yield i

        # Usage:
        result = my_func.sync(42)            # Sync
        for item in my_generator.sync(3):   # iteration
            print(item)
    """
    if inspect.iscoroutinefunction(func):
        return AsyncExecutor(func, is_bound=False)
    if inspect.isasyncgenfunction(func):
        return AsyncIteratorExecutor(func, is_bound=False)
    msg = f"@function_spawner can only be applied to async fns / generators, got {func}"
    raise TypeError(msg)


if __name__ == "__main__":

    @function_spawner
    async def async_func(x: int) -> str:
        """Async function example."""
        return f"result: {x}"

    @function_spawner
    async def async_gen(n: int):
        """Async generator example."""
        for i in range(n):
            await asyncio.sleep(1)  # Simulate async work
            yield i

    # result = async_func.sync(42)
    items = async_gen.sync(3)
    for item in items:
        print("yielded", item)
