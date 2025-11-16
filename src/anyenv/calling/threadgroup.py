"""ThreadGroup module."""

from __future__ import annotations

import concurrent.futures
import contextvars
import logging
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType


class ContextExecutor(concurrent.futures.ThreadPoolExecutor):
    """Thread pool executor that preserves context variables across threads.

    This executor captures the current context variables when created and
    initializes each worker thread with this context.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        """Initialize with the current context variables.

        Args:
            max_workers: Maximum number of worker threads to use
        """
        self.context = contextvars.copy_context()
        super().__init__(max_workers=max_workers, initializer=self._set_child_context)

    def _set_child_context(self) -> None:
        """Set the captured context variables in the worker thread."""
        for var, value in self.context.items():
            var.set(value)


class ThreadGroup[R = Any]:
    """Class that executes functions in parallel, with TaskGroup-like API."""

    def __init__(
        self,
        max_workers: int | None = None,
        raise_exceptions: bool = True,
        preserve_context: bool = False,
    ) -> None:
        """Thread task group that executes functions in parallel.

        Supports both sync and async context managers.

        Args:
            max_workers: Maximum number of worker threads
            raise_exceptions: If True, raises exceptions from tasks
            preserve_context: If True, preserves context variables across threads
        """
        self.max_workers = max_workers
        self.raise_exceptions = raise_exceptions
        self.preserve_context = preserve_context

        if preserve_context:
            self.executor: concurrent.futures.ThreadPoolExecutor = ContextExecutor(
                max_workers=self.max_workers
            )
        else:
            self.executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            )

        self.futures: list[concurrent.futures.Future[R]] = []
        self._results: list[R] = []
        self._exceptions: list[Exception] = []
        self._logger = logging.getLogger(self.__class__.__name__)

    def spawn(
        self, func: Callable[..., R], *args: Any, **kwargs: Any
    ) -> concurrent.futures.Future[R]:
        """Submit a task immediately to the executor.

        Args:
            func: The function to execute
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Future object representing the execution of the function
        """
        future = self.executor.submit(func, *args, **kwargs)
        self.futures.append(future)
        return future

    def __enter__(self) -> ThreadGroup[R]:
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager, collecting results from all futures."""
        for future in concurrent.futures.as_completed(self.futures):
            try:
                result = future.result()
                self._results.append(result)
            except Exception as e:
                self._exceptions.append(e)
                self._logger.exception("Task error")
                if self.raise_exceptions:
                    raise

        self.futures = []

    async def __aenter__(self) -> ThreadGroup[R]:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager."""
        self.__exit__(exc_type, exc_val, exc_tb)

    def shutdown(self) -> None:
        """Shutdown the executor when done with the ThreadGroup."""
        self.executor.shutdown()

    @property
    def results(self) -> list[R]:
        """List of results from completed tasks."""
        return self._results

    @property
    def exceptions(self) -> list[Exception]:
        """List of exceptions raised by tasks."""
        return self._exceptions


if __name__ == "__main__":
    # Example using context variables
    ctx_var = contextvars.ContextVar("example", default="default")

    def test_with_context() -> str:
        """Test for context preservation."""
        return ctx_var.get()

    # Set a value in the main thread
    ctx_var.set("main thread value")

    # Without context preservation
    with ThreadGroup[str](preserve_context=False) as tg:
        tg.spawn(test_with_context)
    print("Without context:", tg.results)

    # With context preservation
    with ThreadGroup[str](preserve_context=True) as tg:
        tg.spawn(test_with_context)
    print("With context:", tg.results)
