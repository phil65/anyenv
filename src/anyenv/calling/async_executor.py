"""Decorator to add sync() method to async functions."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import concurrent.futures
from functools import wraps
import inspect
import queue
import threading
import types
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    Self,
    Union,
    get_args,
    get_origin,
    overload,
)
import warnings

from anyenv.calling.multieventhandler import MultiEventHandler


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Iterator

    from anyenv.calling.multieventhandler import ExecutionMode

from collections.abc import Callable


class AsyncExecutor[**P, T]:
    """Wrapper that provides both async __call__ and sync() methods."""

    def __init__(self, func: Callable[..., Awaitable[T]], *, is_bound: bool) -> None:
        self._func = func
        self._instance: Any = None
        self._is_bound = is_bound
        # Initialize observer system
        self._observers = MultiEventHandler[Callable[[T], Any]]()
        self._observer_mode: ExecutionMode = "parallel"
        # Track filtered handlers by type for cleanup
        self._filtered_handlers: dict[
            tuple[type, ...] | tuple[str, int],
            list[tuple[Callable[[T], Any], Callable[[Any], Any]]],
        ] = defaultdict(list)
        # Copy function metadata
        wraps(func)(self)

    def __get__(self, instance: Any, owner: type | None = None) -> AsyncExecutor[P, T]:
        """Descriptor protocol for method binding."""
        if instance is None:
            return self

        # Cache bound instances per object instance to maintain observer state
        if not hasattr(instance, "_async_executor_cache"):
            instance._async_executor_cache = {}  # noqa: SLF001

        cache_key = id(self)
        if cache_key not in instance._async_executor_cache:  # noqa: SLF001
            # Create bound wrapper to track instance
            bound = type(self)(self._func, is_bound=self._is_bound)
            bound._instance = instance  # noqa: SLF001
            # Each bound instance gets its own isolated observer state
            # (observers, observer_mode, and filtered_handlers are
            # already initialized by __init__)
            instance._async_executor_cache[cache_key] = bound  # noqa: SLF001

        return instance._async_executor_cache[cache_key]  # noqa: SLF001

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Async call - normal behavior."""
        if self._instance is not None and self._is_bound:
            # We're bound to an instance, prepend it to args
            result = await self._func(self._instance, *args, **kwargs)
        else:
            result = await self._func(*args, **kwargs)

        # Emit to all observers
        if self._observers:
            await self._observers.call_handlers(self._observer_mode, result)

        return result

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

    def connect(self, handler: Callable[[T], Any]) -> None:
        """Add observer that will be called with the function's return value."""
        self._observers.add_handler(handler)

    def disconnect(self, handler: Callable[[T], Any]) -> None:
        """Remove observer."""
        self._observers.remove_handler(handler)

    def clear_observers(self) -> None:
        """Remove all observers."""
        self._observers.clear()
        self._filtered_handlers.clear()

    @property
    def observer_count(self) -> int:
        """Number of connected observers."""
        return len(self._observers)

    @property
    def observer_mode(self) -> ExecutionMode:
        """Sequential or parallel observer execution."""
        return self._observer_mode

    @observer_mode.setter
    def observer_mode(self, mode: ExecutionMode) -> None:
        self._observer_mode = mode

    def __getitem__[E](
        self, event_types: type[E] | types.UnionType
    ) -> EventFilteredConnection[E]:
        """Get filtered connection for specific event type(s).

        Args:
            event_types: Single type or union of types to filter for

        Returns:
            EventFilteredConnection that only triggers for matching event types

        Example:
            my_iterator[MyEvent].connect(handler)
            my_iterator[MyEvent | AnotherEvent].connect(handler)
        """
        # Handle union types
        if isinstance(event_types, types.UnionType):
            # Python 3.10+ union syntax: X | Y
            type_tuple = event_types.__args__
        elif get_origin(event_types) is Union:  # type: ignore[arg-type]
            # typing.Union syntax: Union[X, Y]
            type_tuple = get_args(event_types)  # type: ignore[assignment]
        else:
            # Single type
            type_tuple = (event_types,)
        return EventFilteredConnection(self, type_tuple)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped function."""
        return getattr(self._func, name)


class EventFilteredConnection[E]:
    """Filtered connection proxy for specific event types."""

    def __init__(
        self,
        executor: AsyncExecutor[Any, Any] | AsyncIteratorExecutor[Any, Any],
        event_types: tuple[type, ...],
    ) -> None:
        self._executor = executor
        self._event_types = event_types

    def connect(self, handler: Callable[[E], Any]) -> None:
        """Connect handler to filtered events."""
        # Check if handler is already connected for these types
        handlers_list = self._executor._filtered_handlers[self._event_types]  # noqa: SLF001
        for original_handler, _ in handlers_list:
            if original_handler is handler:
                return

        # Create filtered handler wrapper
        async def filtered_handler(event: Any) -> Any:
            if isinstance(event, self._event_types):
                if inspect.iscoroutinefunction(handler):
                    return await handler(event)  # type: ignore[arg-type]
                return handler(event)  # type: ignore[arg-type]
            return None

        # Store mapping and add to observer system
        handlers_list.append((handler, filtered_handler))
        self._executor._observers.add_handler(filtered_handler)  # noqa: SLF001

    def disconnect(self, handler: Callable[[E], Any]) -> None:
        """Disconnect handler from filtered events."""
        if self._event_types not in self._executor._filtered_handlers:  # noqa: SLF001
            return

        handlers_list = self._executor._filtered_handlers[self._event_types]  # noqa: SLF001

        for i, (original_handler, filtered_handler) in enumerate(handlers_list):
            if original_handler is handler:
                # Remove from observer system and our tracking
                self._executor._observers.remove_handler(filtered_handler)  # noqa: SLF001
                handlers_list.pop(i)
                # Clean up empty entries
                if not handlers_list:
                    del self._executor._filtered_handlers[self._event_types]  # noqa: SLF001
                break

    def clear(self) -> None:
        """Clear all handlers for this event filter."""
        if self._event_types not in self._executor._filtered_handlers:  # noqa: SLF001
            return

        handlers_list = self._executor._filtered_handlers[self._event_types]  # noqa: SLF001
        handlers_to_remove = [handler for handler, _ in handlers_list]
        for handler in handlers_to_remove:
            self.disconnect(handler)


class AsyncIteratorExecutor[**P, T]:
    """Wrapper that provides both async __call__ and sync() methods for async gens."""

    def __init__(self, func: Callable[..., AsyncIterator[T]], *, is_bound: bool) -> None:
        self._func = func
        self._instance: Any = None
        self._is_bound = is_bound
        # Initialize observer system for each yielded item
        self._observers = MultiEventHandler[Callable[[T], Any]]()
        self._observer_mode: ExecutionMode = "parallel"
        # Track filtered handlers by type for cleanup
        self._filtered_handlers: dict[
            tuple[type, ...] | tuple[str, int],
            list[tuple[Callable[[T], Any], Callable[[Any], Any]]],
        ] = defaultdict(list)
        # Copy function metadata
        wraps(func)(self)

    def __get__(
        self, instance: Any, owner: type | None = None
    ) -> AsyncIteratorExecutor[P, T]:
        """Descriptor protocol for method binding."""
        if instance is None:
            return self

        # Cache bound instances per object instance to maintain observer state
        if not hasattr(instance, "_async_executor_cache"):
            instance._async_executor_cache = {}  # noqa: SLF001

        cache_key = id(self)
        if cache_key not in instance._async_executor_cache:  # noqa: SLF001
            # Create bound wrapper to track instance
            bound = type(self)(self._func, is_bound=self._is_bound)
            bound._instance = instance  # noqa: SLF001
            # Each bound instance gets its own isolated observer state
            # (observers, observer_mode, and filtered_handlers are already
            # initialized by __init__)
            instance._async_executor_cache[cache_key] = bound  # noqa: SLF001

        return instance._async_executor_cache[cache_key]  # noqa: SLF001

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
        """Return the async iterator with observer emission."""
        if self._instance is not None and self._is_bound:
            # We're bound to an instance, prepend it to args
            async_iter = self._func(self._instance, *args, **kwargs)
        else:
            async_iter = self._func(*args, **kwargs)

        async for item in async_iter:
            # Emit each item to observers
            if self._observers:
                await self._observers.call_handlers(self._observer_mode, item)
            yield item

    def sync(self, *args: P.args, **kwargs: P.kwargs) -> Iterator[T]:
        """Synchronous version that returns a truly lazy iterator."""

        class LazyAsyncIterator:
            def __init__(
                self,
                async_iter_func: Callable[..., AsyncIterator[Any]],
            ) -> None:
                self.async_iter_func = async_iter_func
                self.q: queue.Queue[T | Exception | object] = queue.Queue()
                self.thread: threading.Thread | None = None
                self.started = False
                self.sentinel = object()  # Unique sentinel for end

            def _run_async(self) -> None:
                async def collect() -> None:
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

            def __iter__(self) -> Self:
                return self

            def __next__(self) -> Any:
                if not self.started:
                    self.thread = threading.Thread(target=self._run_async, daemon=True)
                    self.thread.start()
                    self.started = True

                item = self.q.get()
                if item is self.sentinel:
                    raise StopIteration
                if isinstance(item, Exception):
                    raise item
                return item  # pyright: ignore[reportReturnType]

        return LazyAsyncIterator(lambda: self(*args, **kwargs))  # type: ignore[return-value]

    def task(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[list[T]]:
        """Create a Task that collects all values into a list."""

        async def _collect() -> list[T]:
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

        async def _collect() -> list[T]:
            return [item async for item in self(*args, **kwargs)]

        return await asyncio.wait_for(_collect(), timeout_sec)

    def connect(
        self,
        handler: Callable[[T], Any],
        *,
        event_filter: Callable[[T], bool] | None = None,
    ) -> None:
        """Add observer that will be called with each yielded item.

        Args:
            handler: The callback function to connect
            event_filter: Optional filter function to selectively handle events
        """
        if event_filter is None:
            self._observers.add_handler(handler)
        else:
            # Create filtered handler wrapper
            async def filtered_handler(event: T) -> Any:
                if event_filter(event):
                    if inspect.iscoroutinefunction(handler):
                        return await handler(event)
                    return handler(event)
                return None

            # Store with a special key for lambda filters
            lambda_key = ("__lambda_filter__", id(event_filter))
            self._filtered_handlers[lambda_key].append((handler, filtered_handler))
            self._observers.add_handler(filtered_handler)

    def disconnect(self, handler: Callable[[T], Any]) -> None:
        """Remove observer."""
        # Check if it's a filtered handler
        found_and_removed = False
        for event_types, handlers_list in list(self._filtered_handlers.items()):
            for i, (original_handler, filtered_handler) in enumerate(handlers_list):
                if original_handler is handler:
                    self._observers.remove_handler(filtered_handler)
                    handlers_list.pop(i)
                    if not handlers_list:
                        del self._filtered_handlers[event_types]
                    found_and_removed = True
                    break
            if found_and_removed:
                break

        if not found_and_removed:
            self._observers.remove_handler(handler)

    def clear_observers(self) -> None:
        """Remove all observers."""
        self._observers.clear()
        self._filtered_handlers.clear()

    @property
    def observer_count(self) -> int:
        """Number of connected observers."""
        return len(self._observers)

    @property
    def observer_mode(self) -> ExecutionMode:
        """Sequential or parallel observer execution."""
        return self._observer_mode

    @observer_mode.setter
    def observer_mode(self, mode: ExecutionMode) -> None:
        self._observer_mode = mode

    def __getitem__[E](
        self, event_types: type[E] | types.UnionType
    ) -> EventFilteredConnection[E]:
        """Get filtered connection for specific event type(s).

        Args:
            event_types: Single type or union of types to filter for

        Returns:
            EventFilteredConnection that only triggers for matching event types

        Example:
            my_iterator[MyEvent].connect(handler)
            my_iterator[MyEvent | AnotherEvent].connect(handler)
        """
        # Handle union types
        if isinstance(event_types, types.UnionType):
            # Python 3.10+ union syntax: X | Y
            type_tuple = event_types.__args__
        elif get_origin(event_types) is Union:  # type: ignore[arg-type]
            # typing.Union syntax: Union[X, Y]
            type_tuple = get_args(event_types)  # type: ignore[assignment]
        else:
            # Single type
            type_tuple = (event_types,)
        return EventFilteredConnection(self, type_tuple)

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


def method_spawner[**P, T](
    func: Callable[Concatenate[Any, P], Awaitable[T] | AsyncIterator[T]],
) -> AsyncExecutor[P, T] | AsyncIteratorExecutor[P, T]:
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


def function_spawner[**P, T](
    func: Callable[P, Awaitable[T] | AsyncIterator[T]],
) -> AsyncExecutor[P, T] | AsyncIteratorExecutor[P, T]:
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
    import dataclasses

    @dataclasses.dataclass
    class StartEvent:
        """Start event."""

        message: str

    @dataclasses.dataclass
    class DataEvent:
        """Data event."""

        value: int

    @dataclasses.dataclass
    class EndEvent:
        """End event."""

        total: int

    @function_spawner
    async def event_stream() -> AsyncIterator[StartEvent | DataEvent | EndEvent]:
        """Event stream example with filtering."""
        yield StartEvent("Starting process")
        for i in range(3):
            yield DataEvent(i * 10)
        yield EndEvent(total=30)

    def start_handler(event: StartEvent) -> None:
        """Start event handler."""
        print(f"🚀 {event.message}")

    def data_handler(event: DataEvent) -> None:
        """Data event handler."""
        print(f"📊 Data: {event.value}")

    def end_handler(event: EndEvent) -> None:
        """End event handler."""
        print(f"✅ Finished with total: {event.total}")

    def data_or_end_handler(event: DataEvent | EndEvent) -> None:
        """Union event handler."""
        print(f"🔄 Union handler: {type(event).__name__}")

    # Connect specific event handlers
    event_stream[StartEvent].connect(start_handler)
    event_stream[DataEvent].connect(data_handler)
    event_stream[EndEvent].connect(end_handler)

    # Union type filtering works too
    event_stream[DataEvent | EndEvent].connect(data_or_end_handler)

    # Run synchronously
    for _ in event_stream.sync():
        pass  # Handlers are called automatically
