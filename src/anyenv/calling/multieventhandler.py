"""Generic async callback manager for handling multiple event handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
import contextlib
import inspect
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, overload


if TYPE_CHECKING:
    from collections.abc import Awaitable


ExecutionMode = Literal["sequential", "parallel", "task"]
DefaultMode = Literal["parallel"]

# Generic handler type bound to callable returning Any or Awaitable[Any]
P = ParamSpec("P")
HandlerT = Callable[P, Any]


class MultiEventHandler[HandlerT, Mode: ExecutionMode = DefaultMode]:
    """Manages multiple callbacks/event handlers with various execution modes.

    Provides a unified interface for executing multiple callbacks either sequentially,
    in parallel, or as background tasks, with support for dynamic handler management
    and optional debouncing. Sync functions are automatically wrapped to work with
    the async interface.

    The generic parameters HandlerT and Mode provide type safety:
    - HandlerT: callable type (function signature)
    - Mode: execution mode literal for return type inference

    Args:
        handlers: Initial list of async or sync callable event handlers, or single handler
        mode: Execution mode - "sequential", "parallel", or "task"
        debounce_delay: Optional delay in seconds for debouncing rapid calls

    Example:
        ```python
        from collections.abc import Awaitable
        from typing import Callable, Literal

        async def async_handler(x: int, y: str) -> str:
            return f"Async Handler: {x}, {y}"

        def sync_handler(x: int, y: str) -> str:
            return f"Sync Handler: {x}, {y}"

        # Type-safe handler with task mode
        Handler = Callable[[int, str], str | Awaitable[str]]
        manager = MultiEventHandler[Handler, Literal["task"]](
            [async_handler, sync_handler],
            "task",
            debounce_delay=0.1
        )
        tasks: list[asyncio.Task[Any]] = await manager(42, "test")
        ```
    """

    def __init__(
        self,
        handlers: Sequence[HandlerT] | HandlerT | None = None,
        mode: Mode = "parallel",  # type: ignore[assignment]
        debounce_delay: float | None = None,
    ) -> None:
        self._handlers: list[HandlerT] = []
        self._wrapped_handlers: list[Callable[..., Awaitable[Any]]] = []
        self._handler_mapping: dict[HandlerT, Callable[..., Awaitable[Any]]] = {}
        self._mode: Mode = mode
        self._debounce_delay = debounce_delay
        self._debounce_task: asyncio.Task[Any] | None = None

        if handlers is not None:
            match handlers:
                case Sequence():
                    for handler in handlers:
                        self.add_handler(handler)
                case _:
                    # Single handler
                    self.add_handler(handlers)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute all handlers with the configured mode and debouncing.

        Returns:
            - For "sequential"/"parallel": list[Any] (handler results)
            - For "task": list[asyncio.Task[Any]] (task objects)
        """
        if self._debounce_delay is not None:
            return await self._execute_debounced(self._mode, *args, **kwargs)
        return await self._execute_handlers(self._mode, *args, **kwargs)

    @overload
    async def call_handlers(
        self, mode: Literal["task"], *args: Any, **kwargs: Any
    ) -> list[asyncio.Task[Any]]: ...

    @overload
    async def call_handlers(
        self, mode: Literal["sequential", "parallel"], *args: Any, **kwargs: Any
    ) -> list[Any]: ...

    async def call_handlers(
        self, mode: ExecutionMode, *args: Any, **kwargs: Any
    ) -> list[Any] | list[asyncio.Task[Any]]:
        """Execute handlers with explicit mode, bypassing configured mode and debouncing.

        Args:
            mode: Execution mode to use for this call
            *args: Arguments to pass to handlers
            **kwargs: Keyword arguments to pass to handlers

        Returns:
            - For "sequential"/"parallel": list[Any] (handler results)
            - For "task": list[asyncio.Task[Any]] (task objects)
        """
        return await self._execute_handlers(mode, *args, **kwargs)

    async def _execute_debounced(
        self, mode: ExecutionMode, *args: Any, **kwargs: Any
    ) -> list[Any] | list[asyncio.Task[Any]]:
        """Execute handlers with debouncing - cancels previous pending call."""
        # Cancel previous debounced task if it exists
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()

        # Create new debounced task
        async def debounced_execution() -> list[Any] | list[asyncio.Task[Any]]:
            if self._debounce_delay is not None:
                await asyncio.sleep(self._debounce_delay)
            return await self._execute_handlers(mode, *args, **kwargs)

        self._debounce_task = asyncio.create_task(debounced_execution())
        return await self._debounce_task

    async def _execute_handlers(
        self, mode: ExecutionMode, *args: Any, **kwargs: Any
    ) -> list[Any] | list[asyncio.Task[Any]]:
        """Execute handlers with specified mode."""
        if not self._wrapped_handlers:
            return []

        match mode:
            case "sequential":
                return await self._execute_sequential(*args, **kwargs)
            case "parallel":
                return await self._execute_parallel(*args, **kwargs)
            case "task":
                return self._execute_as_tasks(*args, **kwargs)

    async def _execute_sequential(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Execute handlers sequentially."""
        return [await handler(*args, **kwargs) for handler in self._wrapped_handlers]

    async def _execute_parallel(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Execute handlers in parallel using asyncio.gather."""
        tasks = [handler(*args, **kwargs) for handler in self._wrapped_handlers]
        return await asyncio.gather(*tasks)

    def _execute_as_tasks(self, *args: Any, **kwargs: Any) -> list[asyncio.Task[Any]]:
        """Execute handlers as background tasks (non-blocking)."""
        tasks: list[asyncio.Task[Any]] = []
        for handler in self._wrapped_handlers:
            result = handler(*args, **kwargs)
            # Ensure we have a coroutine for asyncio.create_task
            if inspect.iscoroutine(result):
                task = asyncio.create_task(result)
            else:
                # If it's not a coroutine, wrap it in one
                async def wrapper(captured_result: Any = result) -> Any:
                    return captured_result

                task = asyncio.create_task(wrapper())
            tasks.append(task)
        return tasks

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
    def mode(self) -> Mode:
        """Current execution mode."""
        return self._mode

    @property
    def debounce_delay(self) -> float | None:
        """Current debounce delay in seconds."""
        return self._debounce_delay

    @debounce_delay.setter
    def debounce_delay(self, value: float | None) -> None:
        """Set debounce delay in seconds."""
        self._debounce_delay = value

    def __len__(self) -> int:
        """Return number of handlers."""
        return len(self._handlers)

    def __bool__(self) -> bool:
        """Return True if there are handlers registered."""
        return bool(self._handlers)

    def __repr__(self) -> str:
        """Return string representation showing handlers, mode, and debounce."""
        handler_names = [
            h.__qualname__ if hasattr(h, "__qualname__") else repr(h)
            for h in self._handlers
        ]
        debounce_info = (
            f", debounce={self._debounce_delay}s" if self._debounce_delay else ""
        )
        return (
            f"MultiEventHandler(handlers={handler_names}, "
            f"mode={self._mode!r}{debounce_info})"
        )


if __name__ == "__main__":
    from typing import Literal

    type HandlerType = Callable[[int, str], Any]

    def handler(a: int, b: str) -> None:
        """Handler function."""
        print(f"Handler: {a}, {b}")

    async def async_handler(a: int, b: str) -> None:
        """Async handler function."""
        await asyncio.sleep(0.1)
        print(f"Async Handler: {a}, {b}")

    class SomeClass:
        """Some class."""

        def __call__(self, a: int, b: str) -> None:
            """Test class call method."""
            print(f"Class Handler: {a}, {b}")

    # Test type-safe usage
    task_handler = MultiEventHandler[HandlerType, Literal["task"]](
        [handler, async_handler], "task"
    )
    parallel_handler = MultiEventHandler[HandlerType, Literal["parallel"]](
        [handler, SomeClass()], "parallel", debounce_delay=0.1
    )

    print(task_handler)
    print(parallel_handler)

    # Demo usage (would need to run in async context)
    async def demo() -> None:
        """Demo the handlers."""
        # Type-safe task execution
        tasks = await task_handler(42, "test")
        print(f"Created {len(tasks)} tasks")

        # Debounced parallel execution
        results = await parallel_handler(1, "hello")
        print(f"Parallel results: {results}")

        # Runtime mode switching
        task_results = await parallel_handler.call_handlers("task", 2, "world")
        print(f"Task mode results: {len(task_results)} tasks")

    # Uncomment to run demo
    # asyncio.run(demo())
