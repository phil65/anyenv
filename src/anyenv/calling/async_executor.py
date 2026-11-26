"""Decorator to add sync() method to async functions."""

import asyncio
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor  # not the lazy facade (3.15)
import contextlib
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
    from collections.abc import AsyncIterator, Awaitable

    from anyenv.calling.multieventhandler import ExecutionMode

from collections.abc import Callable


# asyncio keeps only weak references to tasks: fire-and-forget ones live here.
_background_tasks: set[asyncio.Task[Any]] = set()
_cache_lock = threading.Lock()


def _keep_alive[TaskT: asyncio.Task[Any]](task: TaskT) -> TaskT:
    _background_tasks.add(task)

    def done(t: asyncio.Task[Any]) -> None:
        _background_tasks.discard(t)
        if not t.cancelled():
            t.exception()  # retrieved: no "exception was never retrieved" warning

    task.add_done_callback(done)
    return task


def _bound_cache(instance: Any) -> dict[int, Any]:
    """The instance's cache of bound executors, created once even across threads."""
    cache = getattr(instance, "_async_executor_cache", None)
    if cache is None:
        with _cache_lock:
            cache = getattr(instance, "_async_executor_cache", None)
            if cache is None:
                cache = {}
                instance._async_executor_cache = cache  # noqa: SLF001
    return cache


def _in_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class _Failure:
    """An exception raised by the generator, passed to the consumer."""

    __slots__ = ("error",)

    def __init__(self, error: Exception) -> None:
        self.error = error


_END = object()
_POLL_INTERVAL = 0.01


class _Producer:
    """Runs the generator in its own thread and loop; holds no reference to the iterator.

    (Otherwise the running thread would keep a dropped iterator alive forever.)
    """

    def __init__(self, factory: Callable[[], AsyncIterator[Any]], maxsize: int) -> None:
        self.factory = factory
        self.queue: queue.Queue[Any] = queue.Queue(maxsize)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task[Any] | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    async def _put(self, item: Any) -> bool:
        """Queue an item without blocking the loop; False once stopped."""
        while not self.stop.is_set():
            try:
                self.queue.put_nowait(item)
            except queue.Full:
                await asyncio.sleep(_POLL_INTERVAL)
            else:
                return True
        return False

    async def _produce(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        self.ready.set()
        if self.stop.is_set():
            return
        agen = self.factory()
        try:
            async for item in agen:
                if not await self._put(item):
                    break
        except asyncio.CancelledError:
            pass  # stopped while the generator was awaiting something
        except Exception as e:  # noqa: BLE001
            await self._put(_Failure(e))
        finally:
            if aclose := getattr(agen, "aclose", None):
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await aclose()
            await self._put(_END)

    def _run(self) -> None:
        try:
            asyncio.run(self._produce())
        finally:
            self.ready.set()

    def signal_stop(self) -> None:
        self.stop.set()
        if self.thread is None:
            return
        self.ready.wait(5)
        if self.loop is not None and self.task is not None:
            with contextlib.suppress(RuntimeError):  # the loop has already finished
                self.loop.call_soon_threadsafe(self.task.cancel)

    def join(self) -> None:
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join()


class LazyAsyncIterator[T]:
    """Iterate an async generator synchronously, from a producer thread.

    The producer runs the generator on its own event loop and stays at most
    ``maxsize`` items ahead (a bounded queue). ``close()``, also called when the
    iterator is garbage-collected, stops the producer and ``aclose()``s the generator.
    """

    def __init__(
        self, async_iter_func: Callable[[], AsyncIterator[T]], *, maxsize: int = 16
    ) -> None:
        self._producer = _Producer(async_iter_func, maxsize)
        self._finished = False

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> T:
        if self._finished:
            raise StopIteration
        if self._producer.thread is None:
            self._producer.start()
        item = self._producer.queue.get()
        if item is _END:
            self._finished = True
            raise StopIteration
        if isinstance(item, _Failure):
            raise item.error
        return item  # type: ignore[no-any-return]

    def close(self) -> None:
        """Stop the producer and close the generator; returns once both are done."""
        self._finished = True
        self._producer.signal_stop()
        self._producer.join()

    def __del__(self) -> None:
        # No join: a finalizer must not block (it may run in any thread).
        with contextlib.suppress(Exception):
            self._producer.signal_stop()


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
        cache = _bound_cache(instance)
        cache_key = id(self)
        if cache_key not in cache:
            # Create bound wrapper to track instance
            bound = type(self)(self._func, is_bound=self._is_bound)
            bound._instance = instance  # noqa: SLF001
            # Each bound instance gets its own isolated observer state
            # (observers, observer_mode, and filtered_handlers are
            # already initialized by __init__)
            # setdefault: a thread that got here first wins, all callers share it.
            cache.setdefault(cache_key, bound)

        return cache[cache_key]  # type: ignore[no-any-return]

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

            def run_coro() -> T:
                return asyncio.run(coro)

            with ThreadPoolExecutor() as executor:
                return executor.submit(run_coro).result()

    def task(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
        """Create a Task for concurrent execution."""
        return asyncio.create_task(self(*args, **kwargs))

    def submit(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
        """Fire-and-forget execution, returns Task but doesn't need to be awaited."""
        return _keep_alive(self.task(*args, **kwargs))

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

    def __getitem__[E](self, event_types: type[E] | types.UnionType) -> EventFilteredConnection[E]:
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
        elif get_origin(event_types) is Union:
            # typing.Union syntax: Union[X, Y]
            type_tuple = get_args(event_types)
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

    def __get__(self, instance: Any, owner: type | None = None) -> AsyncIteratorExecutor[P, T]:
        """Descriptor protocol for method binding."""
        if instance is None:
            return self

        # Cache bound instances per object instance to maintain observer state
        cache = _bound_cache(instance)
        cache_key = id(self)
        if cache_key not in cache:
            # Create bound wrapper to track instance
            bound = type(self)(self._func, is_bound=self._is_bound)
            bound._instance = instance  # noqa: SLF001
            # Each bound instance gets its own isolated observer state
            # (observers, observer_mode, and filtered_handlers are already
            # initialized by __init__)
            # setdefault: a thread that got here first wins, all callers share it.
            cache.setdefault(cache_key, bound)

        return cache[cache_key]  # type: ignore[no-any-return]

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncIterator[T]:
        """Return the async iterator with observer emission."""
        if self._instance is not None and self._is_bound:
            # We're bound to an instance, prepend it to args
            async_iter = self._func(self._instance, *args, **kwargs)
        else:
            async_iter = self._func(*args, **kwargs)

        try:
            async for item in async_iter:
                # Emit each item to observers
                if self._observers:
                    await self._observers.call_handlers(self._observer_mode, item)
                yield item
        finally:
            # Closing this wrapper early closes the wrapped generator too.
            if aclose := getattr(async_iter, "aclose", None):
                await aclose()

    def sync(self, *args: P.args, **kwargs: P.kwargs) -> LazyAsyncIterator[T]:
        """Synchronous version that returns a truly lazy iterator.

        The generator runs in a thread with its own event loop, at most a few items
        ahead of the consumer. ``close()`` (or dropping the iterator) stops it.
        """
        if _in_running_loop():
            warnings.warn(
                "Calling .sync() from async context - using a thread. "
                "Consider using 'async for' instead for better performance.",
                UserWarning,
                stacklevel=2,
            )
        return LazyAsyncIterator(lambda: self(*args, **kwargs))

    def task(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[list[T]]:
        """Create a Task that collects all values into a list."""

        async def _collect() -> list[T]:
            return [item async for item in self(*args, **kwargs)]

        return asyncio.create_task(_collect())

    def submit(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[list[T]]:
        """Fire-and-forget execution that collects all values, returns Task."""
        return _keep_alive(self.task(*args, **kwargs))

    async def timeout(self, timeout_sec: float, *args: P.args, **kwargs: P.kwargs) -> list[T]:
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

    def __getitem__[E](self, event_types: type[E] | types.UnionType) -> EventFilteredConnection[E]:
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
        elif get_origin(event_types) is Union:
            # typing.Union syntax: Union[X, Y]
            type_tuple = get_args(event_types)
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
    event_stream[DataEvent | EndEvent].connect(data_or_end_handler)  # pyright: ignore[reportArgumentType]

    # Run synchronously
    for _ in event_stream.sync():
        pass  # Handlers are called automatically
