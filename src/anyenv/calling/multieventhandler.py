"""Generic async callback manager for handling multiple event handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
import contextlib
import inspect
from typing import TYPE_CHECKING, Any, Literal, ParamSpec


if TYPE_CHECKING:
    from collections.abc import Awaitable


ExecutionMode = Literal["sequential", "parallel"]

# Generic handler type bound to callable returning Any or Awaitable[Any]
P = ParamSpec("P")
HandlerT = Callable[P, Any]


class MultiEventHandler[HandlerT]:
    """Manages multiple callbacks/event handlers with sequential or parallel execution.

    Provides a unified interface for executing multiple callbacks either sequentially
    or in parallel, with support for dynamic handler management. Sync functions are
    automatically wrapped to work with the async interface.

    The generic parameter HandlerT should be a callable type (function signature).

    Args:
        handlers: Initial list of async or sync callable event handlers, or single handler
        mode: Execution mode - "sequential" or "parallel"

    Example:
        ```python
        from collections.abc import Awaitable
        from typing import Callable

        async def async_handler(x: int, y: str) -> str:
            return f"Async Handler: {x}, {y}"

        def sync_handler(x: int, y: str) -> str:
            return f"Sync Handler: {x}, {y}"

        # Handler type specification
        Handler = Callable[[int, str], str | Awaitable[str]]
        manager: MultiEventHandler[Handler] = MultiEventHandler([
            async_handler, sync_handler
        ])
        results = await manager(42, "test")
        ```
    """

    def __init__(
        self,
        handlers: Sequence[HandlerT] | HandlerT | None = None,
        mode: ExecutionMode = "parallel",
    ) -> None:
        self._handlers: list[HandlerT] = []
        self._wrapped_handlers: list[Callable[..., Awaitable[Any]]] = []
        self._handler_mapping: dict[HandlerT, Callable[..., Awaitable[Any]]] = {}
        self._mode: ExecutionMode = mode

        if handlers is not None:
            match handlers:
                case Sequence():
                    for handler in handlers:
                        self.add_handler(handler)
                case _:
                    # Single handler
                    self.add_handler(handlers)

    @property
    def __call__(self) -> HandlerT:
        """Execute all handlers with the given arguments.

        Returns:
            List of results from all handlers.
        """

        async def event_handler(*args, **kwargs):
            if not self._wrapped_handlers:
                return []

            if self._mode == "sequential":
                return await self._execute_sequential(*args, **kwargs)
            return await self._execute_parallel(*args, **kwargs)

        return event_handler  # type: ignore

    async def _execute_sequential(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Execute handlers sequentially."""
        return [await handler(*args, **kwargs) for handler in self._wrapped_handlers]

    async def _execute_parallel(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Execute handlers in parallel using asyncio.gather."""
        tasks = [handler(*args, **kwargs) for handler in self._wrapped_handlers]
        return await asyncio.gather(*tasks)

    def add_handler(self, handler: HandlerT) -> None:
        """Add a new handler to the manager.

        Both sync and async handlers are supported.
        """
        if handler in self._handlers:
            return

        # Check if handler is already async (function or callable class)
        if inspect.iscoroutinefunction(handler):
            wrapped_handler = handler
        elif callable(handler) and inspect.iscoroutinefunction(handler.__call__):
            wrapped_handler = handler.__call__
        else:
            # Wrap sync handler
            wrapped_handler = self._wrap_sync_handler(handler)  # type: ignore[assignment]

        self._handlers.append(handler)
        self._wrapped_handlers.append(wrapped_handler)
        self._handler_mapping[handler] = wrapped_handler

    def remove_handler(self, handler: HandlerT) -> None:
        """Remove a handler from the manager.

        Note: For sync handlers, you must pass the original sync function,
        not the wrapped async version.
        """
        if handler not in self._handlers:
            return

        with contextlib.suppress(ValueError):
            # Remove from all tracking structures
            wrapped_handler = self._handler_mapping[handler]
            self._handlers.remove(handler)
            self._wrapped_handlers.remove(wrapped_handler)
            del self._handler_mapping[handler]

    def _wrap_sync_handler(self, handler: HandlerT) -> Callable[..., Awaitable[Any]]:
        """Wrap a synchronous handler to work with async interface."""

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return handler(*args, **kwargs)  # type: ignore[misc,operator]

        # Store reference to original handler for removal
        async_wrapper._original_handler = handler  # type: ignore[attr-defined]  # noqa: SLF001
        return async_wrapper

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._wrapped_handlers.clear()
        self._handler_mapping.clear()

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

    def __repr__(self) -> str:
        """Return string representation showing handlers and mode."""
        handler_names = []
        for handler in self._handlers:
            if hasattr(handler, "__qualname__"):
                handler_names.append(handler.__qualname__)
            else:
                handler_names.append(repr(handler))

        return f"MultiEventHandler(handlers={handler_names}, mode={self._mode!r})"


if __name__ == "__main__":
    type HandlerType = Callable[[int, str], Any]

    def handler(a: int, b: str):
        """Handler function."""

    def invalid_handler(a: str, b: str):
        """Invalid handler function."""

    class SomeClass:
        """Some class."""

        def __call__(self, a: int, b: str):
            """Test class call method."""

    multi_handler = MultiEventHandler[HandlerType]()
    multi_handler.add_handler(handler)
    # multi_handler.add_handler(invalid_handler)
    multi_handler.add_handler(SomeClass())
    print(multi_handler)
