"""Base classes for anyenv HTTP functionality."""

from __future__ import annotations

import abc
from collections.abc import Callable
import inspect
import os
import pathlib
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NotRequired,
    Self,
    TypedDict,
)


if TYPE_CHECKING:
    import types

    from anyenv.download.http_types import (
        AuthType,
        CacheType,
        FilesType,
        HeaderType,
        ParamsType,
        SecretStr,
    )

ProgressCallback = Callable[[int, int], Any]  # current, total -> Any
Method = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
BackendType = Literal["httpx", "aiohttp", "pyodide"]
StrPath = str | os.PathLike[str]
DEFAULT_TTL = 3600


class BaseRequestOptions(TypedDict):
    """Basic options common to all HTTP requests."""

    params: NotRequired[ParamsType | None]
    headers: NotRequired[HeaderType | None]
    timeout: NotRequired[float | None]
    cache: NotRequired[bool]
    backend: NotRequired[BackendType | None]
    cache_dir: NotRequired[StrPath | None]
    cache_ttl: NotRequired[int | str | None]


class AuthOptions(TypedDict):
    """Authentication options for HTTP requests."""

    api_key: NotRequired[str | SecretStr | None]
    auth_type: NotRequired[AuthType]
    auth_username: NotRequired[str | None]
    auth_header_name: NotRequired[str | None]


class DataRetrievalOptions(BaseRequestOptions, AuthOptions):
    """Combined options for data retrieval HTTP requests."""


class HttpResponse(abc.ABC):
    """HTTP response object."""

    @property
    @abc.abstractmethod
    def status_code(self) -> int:
        """HTTP status code."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def reason(self) -> str:
        """Status code of the response."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def url(self) -> str:
        """URL of the response."""
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

    async def validated_json[T](self, return_type: type[T]) -> T:
        """Get response body as JSON and validate against a type.

        Args:
            return_type: The type to validate the response against

        Returns:
            The parsed JSON data, validated against return_type

        Raises:
            TypeError: If validation fails
        """
        from anyenv.validate import validate_json_data

        data = await self.json()
        return validate_json_data(data, return_type)


class Session(abc.ABC):
    """HTTP session for connection reuse."""

    @abc.abstractmethod
    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: ParamsType | None = None,
        headers: HeaderType | None = None,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        timeout: float | None = None,
        cache: bool = False,
    ) -> HttpResponse:
        """Make a request."""
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
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
    ) -> None:
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
    ) -> None:
        """Exit sync context."""
        import anyio

        async def wrapper() -> None:
            await self.__aexit__(exc_type, exc_val, exc_tb)

        anyio.run(wrapper)


class HttpBackend(abc.ABC):
    """Base class for HTTP backend implementations."""

    def __init__(
        self,
        cache_dir: StrPath | None = None,
        cache_ttl: int | str | None = None,
    ) -> None:
        """Initialize HTTP backend.

        Args:
            cache_dir: Directory to store cached responses. If None,
                       uses platform-specific user cache directory.
            cache_ttl: Time-to-live for cached responses in seconds or as a
                        time period string (e.g. "1h", "2d", "1w 2d").
        """
        from appdirs import user_cache_dir

        if isinstance(cache_ttl, str):
            from anyenv.parse_time import parse_time_period

            cache_ttl_seconds = int(parse_time_period(cache_ttl).total_seconds())
        else:
            cache_ttl_seconds = cache_ttl or DEFAULT_TTL
        dir_ = cache_dir or user_cache_dir("anyenv", False)
        self.cache_dir = pathlib.Path(dir_)
        self.cache_ttl = cache_ttl_seconds

    @abc.abstractmethod
    async def request(
        self,
        method: Method,
        url: str,
        *,
        params: ParamsType | None = None,
        headers: HeaderType | None = None,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        timeout: float | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> HttpResponse:
        """Make a request."""
        raise NotImplementedError

    def request_sync(
        self,
        method: Method,
        url: str,
        *,
        params: ParamsType | None = None,
        headers: HeaderType | None = None,
        json: Any = None,
        data: Any = None,
        files: FilesType | None = None,
        timeout: float | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
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
                files=files,
                timeout=timeout,
                cache=cache,
                cache_backend=cache_backend,
            )

        return anyio.run(wrapper)

    @abc.abstractmethod
    async def download(
        self,
        url: str,
        path: StrPath,
        *,
        headers: HeaderType | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> None:
        """Download a file with optional progress reporting."""
        raise NotImplementedError

    def download_sync(
        self,
        url: str,
        path: StrPath,
        *,
        headers: HeaderType | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> None:
        """Synchronous version of download."""
        import anyio

        async def wrapper() -> None:
            await self.download(
                url,
                path,
                headers=headers,
                progress_callback=progress_callback,
                cache=cache,
                cache_backend=cache_backend,
            )

        return anyio.run(wrapper)

    @abc.abstractmethod
    async def create_session(
        self,
        *,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> Session:
        """Create a new session for connection reuse."""
        raise NotImplementedError

    def create_session_sync(
        self,
        *,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> Session:
        """Synchronous version of create_session."""
        import anyio

        async def wrapper() -> Session:
            return await self.create_session(
                base_url=base_url,
                headers=headers,
                cache=cache,
                cache_backend=cache_backend,
            )

        return anyio.run(wrapper)

    async def _handle_callback(
        self,
        callback: ProgressCallback,
        current: int,
        total: int,
    ) -> None:
        """Handle both sync and async callbacks."""
        if inspect.iscoroutinefunction(callback):
            await callback(current, total)
        else:
            callback(current, total)
