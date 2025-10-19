"""Generic async callback manager for handling multiple event handlers."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence


ExecutionMode = Literal["sequential", "parallel"]


class MultiEventHandler[**P, T]:
    """Manages multiple callbacks/event handlers with sequential or parallel execution.

    Provides a unified interface for executing multiple callbacks either sequentially
    or in parallel, with support for dynamic handler management. All handlers must
    have matching signatures enforced by ParamSpec. Sync functions are automatically
    wrapped to work with the async interface.

    Args:
        handlers: Initial list of async or sync callable event handlers
        mode: Execution mode - "sequential" or "parallel"

    Example:
        ```python
        async def async_handler(x: int, y: str) -> str:
            return f"Async Handler: {x}, {y}"

        def sync_handler(x: int, y: str) -> str:
            return f"Sync Handler: {x}, {y}"

        manager = MultiEventHandler([async_handler, sync_handler])
        results = await manager(42, "test")
        ```
    """

    def __init__(
        self,
        handlers: Sequence[Callable[P, T] | Callable[P, Awaitable[T]]] | None = None,
        mode: ExecutionMode = "sequential",
    ) -> None:
        self._handlers: list[Callable[P, Awaitable[T]]] = []
        if handlers:
            for handler in handlers:
                self.add_handler(handler)
        self._mode: ExecutionMode = mode

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> list[T]:
        """Execute all handlers with the given arguments.

        Returns:
            List of results from all handlers.
        """
        if not self._handlers:
            return []

        if self._mode == "sequential":
            return await self._execute_sequential(*args, **kwargs)
        return await self._execute_parallel(*args, **kwargs)

    async def _execute_sequential(self, *args: P.args, **kwargs: P.kwargs) -> list[T]:
        """Execute handlers sequentially."""
        return [await handler(*args, **kwargs) for handler in self._handlers]

    async def _execute_parallel(self, *args: P.args, **kwargs: P.kwargs) -> list[T]:
        """Execute handlers in parallel using asyncio.gather."""
        tasks = [handler(*args, **kwargs) for handler in self._handlers]
        return await asyncio.gather(*tasks)

    def add_handler(self, handler: Callable[P, T] | Callable[P, Awaitable[T]]) -> None:
        """Add a new handler to the manager.

        The handler must match the signature enforced by ParamSpec.
        Both sync and async handlers are supported.
        """
        # Check if handler is already async
        if inspect.iscoroutinefunction(handler):
            wrapped_handler = handler  # type: ignore[assignment]
        else:
            # Wrap sync handler
            wrapped_handler = self._wrap_sync_handler(handler)  # type: ignore

        if wrapped_handler not in self._handlers:
            self._handlers.append(wrapped_handler)

    def remove_handler(self, handler: Callable[P, T] | Callable[P, Awaitable[T]]) -> None:
        """Remove a handler from the manager.

        Note: For sync handlers, you must pass the original sync function,
        not the wrapped async version.
        """
        # Try to find and remove the handler
        # For sync handlers, we need to find the wrapped version
        to_remove = None

        if inspect.iscoroutinefunction(handler):
            # Handler is async, find it directly
            to_remove = handler  # type: ignore[assignment]
        else:
            # Handler is sync, find the wrapped version
            # We'll compare by checking the __wrapped__ attribute we can add
            for wrapped in self._handlers:
                if (
                    hasattr(wrapped, "_original_handler")
                    and wrapped._original_handler is handler  # noqa: SLF001
                ):  # type: ignore[attr-defined]
                    to_remove = wrapped  # type: ignore
                    break

        if to_remove:
            with contextlib.suppress(ValueError):
                self._handlers.remove(to_remove)

    def _wrap_sync_handler(self, handler: Callable[P, T]) -> Callable[P, Awaitable[T]]:
        """Wrap a synchronous handler to work with async interface."""

        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return handler(*args, **kwargs)

        # Store reference to original handler for removal
        async_wrapper._original_handler = handler  # type: ignore[attr-defined]  # noqa: SLF001
        return async_wrapper

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()

    @property
    def mode(self) -> ExecutionMode:
        """Current execution mode."""
        return self._mode

    @mode.setter
    def mode(self, value: ExecutionMode) -> None:
        """Set execution mode."""
        self._mode = value

    def __len__(self) -> int:
        """Return number of handlers."""
        return len(self._handlers)

    def __bool__(self) -> bool:
        """Return True if there are handlers registered."""
        return bool(self._handlers)
