"""Base classes for anyenv HTTP functionality."""

from __future__ import annotations

import abc
from collections.abc import Callable
import inspect
import pathlib
from typing import TYPE_CHECKING, Any, Literal, Self, TypeVar

from appdirs import user_cache_dir


if TYPE_CHECKING:
    from os import PathLike
    import types

T = TypeVar("T")
ProgressCallback = Callable[[int, int], Any]  # current, total -> Any
Method = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
DEFAULT_TTL = 3600


class HttpResponse(abc.ABC):
    """HTTP response object."""

    @property
    @abc.abstractmethod
    def status_code(self) -> int:
        """HTTP status code."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def headers(self) -> dict[str, str]:
        """Response headers."""
        raise NotImplementedError

    @abc.abstractmethod
    async def text(self) -> str:
        """Get response body as text."""
        raise NotImplementedError

    @abc.abstractmethod
    async def json(self) -> Any:
        """Get response body as JSON."""
        raise NotImplementedError

    @abc.abstractmethod
    async def bytes(self) -> bytes:
        """Get response body as bytes."""
        raise NotImplementedError


class Session(abc.ABC):
    """HTTP session for connection reuse."""

    @abc.abstractmethod
    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        timeout: float | None = None,
        cache: bool = False,
    ) -> HttpResponse:
        """Make a request."""
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self):
        """Close the session."""
        raise NotImplementedError

    async def __aenter__(self) -> Self:
        """Enter async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ):
        """Exit async context."""
        await self.close()

    def __enter__(self) -> Self:
        """Enter sync context."""
        import anyio

        async def wrapper() -> Self:
            return await self.__aenter__()

        return anyio.run(wrapper)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ):
        """Exit sync context."""
        import anyio

        async def wrapper():
            await self.__aexit__(exc_type, exc_val, exc_tb)

        anyio.run(wrapper)


class HttpBackend(abc.ABC):
    """Base class for HTTP backend implementations."""

    def __init__(
        self,
        cache_dir: str | PathLike[str] | None = None,
        cache_ttl: int | None = None,
    ):
        """Initialize HTTP backend.

        Args:
            cache_dir: Directory to store cached responses. If None,
                       uses platform-specific user cache directory.
            cache_ttl: Time-to-live for cached responses in seconds.
        """
        cache_ttl = cache_ttl or DEFAULT_TTL
        dir_ = cache_dir or user_cache_dir("anyenv", False)
        self.cache_dir = pathlib.Path(dir_)
        self.cache_ttl = cache_ttl

    @abc.abstractmethod
    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        timeout: float | None = None,
        cache: bool = False,
    ) -> HttpResponse:
        """Make a request."""
        raise NotImplementedError

    def request_sync(
        self,
        method: Method,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        timeout: float | None = None,
        cache: bool = False,
    ) -> HttpResponse:
        """Synchronous version of request."""
        import anyio

        async def wrapper() -> HttpResponse:
            return await self.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json,
                data=data,
                timeout=timeout,
                cache=cache,
            )

        return anyio.run(wrapper)

    @abc.abstractmethod
    async def download(
        self,
        url: str,
        path: str | PathLike[str],
        *,
        headers: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
    ):
        """Download a file with optional progress reporting."""
        raise NotImplementedError

    def download_sync(
        self,
        url: str,
        path: str | PathLike[str],
        *,
        headers: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
    ):
        """Synchronous version of download."""
        import anyio

        async def wrapper():
            await self.download(
                url,
                path,
                headers=headers,
                progress_callback=progress_callback,
                cache=cache,
            )

        return anyio.run(wrapper)

    @abc.abstractmethod
    async def create_session(
        self,
        *,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        cache: bool = False,
    ) -> Session:
        """Create a new session for connection reuse."""
        raise NotImplementedError

    def create_session_sync(
        self,
        *,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        cache: bool = False,
    ) -> Session:
        """Synchronous version of create_session."""
        import anyio

        async def wrapper() -> Session:
            return await self.create_session(
                base_url=base_url,
                headers=headers,
                cache=cache,
            )

        return anyio.run(wrapper)

    async def _handle_callback(
        self,
        callback: ProgressCallback,
        current: int,
        total: int,
    ):
        """Handle both sync and async callbacks."""
        if inspect.iscoroutinefunction(callback):
            await callback(current, total)
        else:
            callback(current, total)
