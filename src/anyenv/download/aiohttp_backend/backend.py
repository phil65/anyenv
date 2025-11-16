"""aiohttp backend implementation for anyenv."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, assert_never

from anyenv import dump_json, load_json
from anyenv.anypath import Path
from anyenv.download.base import HttpBackend, HttpResponse, Session
from anyenv.download.exceptions import RequestError, ResponseError, check_response


if TYPE_CHECKING:
    import os

    import aiohttp
    from aiohttp_client_cache import CacheBackend, CachedSession

    from anyenv.download.base import Method, ProgressCallback, StrPath
    from anyenv.download.http_types import CacheType, FilesType, HeaderType, ParamsType


def get_storage(
    cache_backend: CacheType,
    cache_dir: StrPath,
    cache_ttl: int,
) -> CacheBackend:
    """Get storage backend."""
    from aiohttp_client_cache import CacheBackend, FileBackend, SQLiteBackend

    match cache_backend:
        case "sqlite":
            path = str(Path(cache_dir) / "http_cache.db")
            return SQLiteBackend(cache_name=path, expire_after=cache_ttl)
        case "file":
            return FileBackend(cache_name=str(cache_dir), expire_after=cache_ttl)
        case "memory":
            return CacheBackend(expire_after=cache_ttl)
        case _ as unreachable:
            assert_never(unreachable)


class AiohttpResponse(HttpResponse):
    """aiohttp implementation of HTTP response."""

    def __init__(self, response: aiohttp.ClientResponse) -> None:
        self._response = response

    @property
    def status_code(self) -> int:
        """Status code of the response."""
        return self._response.status

    @property
    def reason(self) -> str:
        """Status code of the response."""
        return self._response.reason or ""

    @property
    def url(self) -> str:
        """URL of the response."""
        return str(self._response.url)

    @property
    def headers(self) -> dict[str, str]:
        """Headers of the response."""
        return dict(self._response.headers)

    async def text(self) -> str:
        """Text content of the response."""
        return await self._response.text()

    async def json(self) -> Any:
        """JSON content of the response."""
        return await self._response.json(loads=load_json)

    async def bytes(self) -> bytes:
        """Bytes content of the response."""
        return await self._response.read()


class AiohttpSession(Session):
    """aiohttp implementation of HTTP session."""

    def __init__(self, session: CachedSession, base_url: str | None = None) -> None:
        self._session = session
        self._base_url = base_url

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
        cache: bool | None = None,  # Changed default to None
    ) -> HttpResponse:
        """Make a request using aiohttp session."""
        import aiohttp
        from aiohttp import FormData

        if self._base_url:
            url = f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

        try:
            if files:
                form = FormData()
                if isinstance(data, dict):
                    for key, value in data.items():
                        form.add_field(key, str(value))
                for field_name, file_info in files.items():
                    match file_info:
                        case str() | bytes() as content:
                            form.add_field(field_name, content)
                        case (str() as filename, content):
                            form.add_field(field_name, content, filename=filename)
                        case (str() as filename, content, str() as content_type):
                            form.add_field(
                                field_name,
                                content,
                                filename=filename,
                                content_type=content_type,
                            )
                        case _:
                            msg = f"Invalid file specification for field {field_name!r}"
                            raise ValueError(msg)
                data = form
            request_headers = dict(headers or {})
            kwargs = {}
            if cache is not None:
                # The aiohttp_client_cache accepts cache_disabled parameter
                kwargs["cache_disabled"] = not cache

                if cache is False:
                    request_headers["Cache-Control"] = "no-store"
                elif cache is True:
                    request_headers["Cache-Control"] = "max-age=3600"

            response = await self._session.request(
                method,
                url,
                params=params,  # type: ignore
                headers=request_headers,
                json=json,
                data=data,
                timeout=aiohttp.ClientTimeout(total=timeout) if timeout else None,
                **kwargs,  # type: ignore
            )
            aiohttp_response = AiohttpResponse(response)
        except aiohttp.ClientError as exc:
            error_msg = f"Request failed: {exc!s}"
            raise RequestError(error_msg) from exc

        return check_response(aiohttp_response)

    async def close(self) -> None:
        """Close the session."""
        await self._session.close()


class AiohttpBackend(HttpBackend):
    """aiohttp implementation of HTTP backend."""

    async def _create_session(
        self,
        cache: bool = False,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache_backend: CacheType = "file",
    ) -> CachedSession:
        from aiohttp_client_cache import CachedSession

        if cache:
            cache_client = get_storage(cache_backend, self.cache_dir, self.cache_ttl)
            return CachedSession(
                cache=cache_client,
                headers=headers,
                base_url=base_url,
                json_serialize=dump_json,
            )

        # Even when not caching, we use CachedSession for consistent interface
        return CachedSession(
            expire_after=0,
            headers=headers,
            base_url=base_url,
            json_serialize=dump_json,
        )

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
        """Make a request using aiohttp backend."""
        import aiohttp
        from aiohttp import FormData

        session = await self._create_session(cache=cache, cache_backend=cache_backend)
        try:
            try:
                # Handle file uploads if present
                if files:
                    form = FormData()

                    # Add regular form data if any
                    if isinstance(data, dict):
                        for key, value in data.items():
                            form.add_field(key, str(value))

                    # Add files
                    for field_name, file_info in files.items():
                        match file_info:
                            case str() | bytes() as content:
                                form.add_field(field_name, content)
                            case (str() as filename, content):
                                form.add_field(field_name, content, filename=filename)
                            case (str() as filename, content, str() as content_type):
                                form.add_field(
                                    field_name,
                                    content,
                                    filename=filename,
                                    content_type=content_type,
                                )
                            case _:
                                msg = (
                                    f"Invalid file specification for field {field_name!r}"
                                )
                                raise ValueError(msg)
                    data = form

                response = await session.request(
                    method,
                    url,
                    params=params,  # type: ignore
                    headers=headers,
                    json=json,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=timeout) if timeout else None,
                )
                aiohttp_response = AiohttpResponse(response)
            except aiohttp.ClientError as exc:
                error_msg = f"Request failed: {exc!s}"
                raise RequestError(error_msg) from exc

            # Check for HTTP status errors
            return check_response(aiohttp_response)
        finally:
            await session.close()

    async def download(
        self,
        url: str,
        path: str | os.PathLike[str],
        *,
        headers: HeaderType | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> None:
        """Download implementation using aiohttp."""
        import aiohttp

        session = await self._create_session(cache=cache, cache_backend=cache_backend)
        try:
            try:
                async with session.get(url, headers=headers) as response:
                    # Check for HTTP errors instead of using raise_for_status()
                    if 400 <= response.status < 600:  # noqa: PLR2004
                        message = f"HTTP Error {response.status}"
                        raise ResponseError(message, AiohttpResponse(response))

                    total = int(response.headers.get("content-length", "0"))
                    current = 0

                    with Path(path).open("wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            current += len(chunk)
                            if progress_callback:
                                await self._handle_callback(
                                    progress_callback, current, total
                                )
            except aiohttp.ClientError as exc:
                error_msg = f"Download failed: {exc!s}"
                raise RequestError(error_msg) from exc
        finally:
            await session.close()

    async def create_session(
        self,
        *,
        base_url: str | None = None,
        headers: HeaderType | None = None,
        cache: bool = False,
        cache_backend: CacheType = "file",
    ) -> Session:
        """Create a new aiohttp session."""
        session = await self._create_session(
            cache=cache,
            base_url=base_url,
            headers=headers,
            cache_backend=cache_backend,
        )
        return AiohttpSession(session, base_url)
