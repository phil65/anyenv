"""Decorator to add sync() method to async functions."""

from __future__ import annotations

import asyncio
import concurrent.futures
from functools import wraps
import inspect
from typing import TYPE_CHECKING, Any
import warnings


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class AsyncExecutor[**P, T]:
    """Wrapper that provides both async __call__ and sync() methods."""

    def __init__(self, func: Callable[P, Awaitable[T]], *, is_bound: bool) -> None:
        self._func = func
        self._instance: Any = None
        self._is_bound = is_bound
        # Copy function metadata
        wraps(func)(self)

    def __get__(self, instance: Any, owner: type | None = None) -> AsyncExecutor[P, T]:
        """Descriptor protocol for method binding."""
        if instance is None:
            return self
        # Always create bound wrapper to track instance for validation
        bound = type(self)(self._func, is_bound=self._is_bound)
        bound._instance = instance  # noqa: SLF001
        return bound

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Async call - normal behavior."""
        # Validate bound/unbound usage before making the call
        if self._instance is not None and not self._is_bound:
            # Error: method used but declared as unbound function
            msg = (
                f"Method {self._func.__name__} was decorated with bound=False "
                "but is being called as a bound method. Use bound=True for methods."
            )
            raise TypeError(msg)
        if self._instance is None and self._is_bound:
            # Check if this looks like a method signature but no instance
            sig = inspect.signature(self._func)
            params = list(sig.parameters.values())
            if params and params[0].name in ("self", "cls"):
                msg = (
                    f"Function {self._func.__name__} was decorated with bound=True "
                    "but is being called as a standalone function. Use bound=False "
                    "for standalone functions."
                )
                raise TypeError(msg)

        # Make the actual call
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

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped function."""
        return getattr(self._func, name)


def async_executor(*, bound: bool):
    """Decorator factory to add sync() method to async functions.

    Args:
        bound: True for methods (have self parameter), False for standalone functions

    Usage:
        # For standalone functions
        @async_executor(bound=False)
        async def my_func(x: int) -> str:
            return str(x)

        # For methods
        class MyClass:
            @async_executor(bound=True)
            async def my_method(self, x: int) -> str:
                return str(x)

        # Both work:
        result = await my_func(42)
        result = my_func.sync(42)
        result = await obj.my_method(42)
        result = obj.my_method.sync(42)
    """

    def decorator[**P, T](func: Callable[P, Awaitable[T]]) -> AsyncExecutor[P, T]:
        if not inspect.iscoroutinefunction(func):
            msg = f"@async_executor can only be applied to async functions, got {func}"
            raise TypeError(msg)
        return AsyncExecutor(func, is_bound=bound)

    return decorator
