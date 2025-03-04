from __future__ import annotations

import concurrent.futures
import logging
from typing import TYPE_CHECKING, Any

from typing_extensions import TypeVar


if TYPE_CHECKING:
    from collections.abc import Callable


R = TypeVar("R", default=Any)


class ThreadGroup[R]:
    def __init__(self, max_workers: int | None = None, raise_exceptions: bool = True):
        """Thread task group that executes functions in parallel.

        Supports both sync and async context managers.

        Args:
            max_workers: Maximum number of worker threads
            raise_exceptions: If True, raises exceptions from tasks
        """
        self.max_workers = max_workers
        self.raise_exceptions = raise_exceptions
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        )
        self.futures: list[concurrent.futures.Future[R]] = []
        self._results: list[R] = []
        self._exceptions: list[Exception] = []
        self._logger = logging.getLogger(self.__class__.__name__)

    def spawn(self, func: Callable[..., R], *args: Any, **kwargs: Any) -> None:
        """Submit a task immediately to the executor."""
        future = self.executor.submit(func, *args, **kwargs)
        self.futures.append(future)

    def __enter__(self) -> ThreadGroup[R]:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
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
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self.__exit__(exc_type, exc_val, exc_tb))

    def shutdown(self) -> None:
        """Shutdown the executor when done with the ThreadGroup."""
        self.executor.shutdown()

    @property
    def results(self) -> list[R]:
        return self._results

    @property
    def exceptions(self) -> list[Exception]:
        return self._exceptions
