"""aiohttp backend implementation for anyenv."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anyenv.anypath import Path
from anyenv.download.base import (
    HttpBackend,
    HttpResponse,
    Method,
    ProgressCallback,
    Session,
)
from anyenv.download.exceptions import RequestError, check_response


if TYPE_CHECKING:
    import os

    import aiohttp
    from aiohttp_client_cache import CachedSession

    from anyenv.download.http_types import CacheType, FilesType, HeaderType, ParamsType


class AiohttpResponse(HttpResponse):
    """aiohttp implementation of HTTP response."""

    def __init__(self, response: aiohttp.ClientResponse):
        self._response = response

    @property
    def status_code(self) -> int:
        """Status code of the response."""
        return self._response.status

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
        from anyenv import load_json

        return await self._response.json(loads=load_json)

    async def bytes(self) -> bytes:
        """Bytes content of the response."""
        return await self._response.read()


class AiohttpSession(Session):
    """aiohttp implementation of HTTP session."""

    def __init__(self, session: CachedSession, base_url: str | None = None):
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
        cache: bool = False,
    ) -> HttpResponse:
        """Make a request using aiohttp session."""
        import aiohttp
        from aiohttp import FormData

        if self._base_url:
            url = f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

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
                            msg = f"Invalid file specification for field {field_name!r}"
                            raise ValueError(msg)
                data = form

            # The CachedSession from aiohttp_client_cache honors cache_disabled parameter
            response = await self._session.request(
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

    async def close(self):
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
        from aiohttp_client_cache import (
            CacheBackend,
            CachedSession,
            FileBackend,
            SQLiteBackend,
        )

        from anyenv import dump_json

        if cache:
            match cache_backend:
                case "sqlite":
                    path = str(self.cache_dir / "http_cache.db")
                    cache_client: CacheBackend = SQLiteBackend(
                        cache_name=path, expire_after=self.cache_ttl
                    )
                case "file":
                    cache_client = FileBackend(
                        cache_name=str(self.cache_dir), expire_after=self.cache_ttl
                    )
                case "memory":
                    cache_client = CacheBackend(expire_after=self.cache_ttl)
                case _:
                    msg = f"Invalid cache backend: {cache_backend}"
                    raise ValueError(msg)
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

        from anyenv.download.exceptions import RequestError, check_response

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
    ):
        """Download implementation using aiohttp."""
        import aiohttp

        from anyenv.download.exceptions import RequestError, ResponseError

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
