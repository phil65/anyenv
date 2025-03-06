"""aiohttp backend implementation for anyenv."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anyenv.download.base import (
    HttpBackend,
    HttpResponse,
    Method,
    ProgressCallback,
    Session,
)
from anyenv.download.exceptions import RequestError, check_response


try:
    from upath import UPath as Path
except ImportError:
    from pathlib import Path  # type: ignore[assignment]

if TYPE_CHECKING:
    import os

    import aiohttp
    from aiohttp_client_cache import CachedSession


class AiohttpResponse(HttpResponse):
    """aiohttp implementation of HTTP response."""

    def __init__(self, response: aiohttp.ClientResponse):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._response.headers)

    async def text(self) -> str:
        return await self._response.text()

    async def json(self) -> Any:
        from anyenv.json_tools import loading

        return await self._response.json(loads=loading.load_json)

    async def bytes(self) -> bytes:
        return await self._response.read()


class AiohttpSession(Session):
    """aiohttp implementation of HTTP session."""

    def __init__(
        self,
        session: CachedSession,
        base_url: str | None = None,
    ):
        self._session = session
        self._base_url = base_url

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
        import aiohttp

        if self._base_url:
            url = f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

        try:
            # The CachedSession from aiohttp_client_cache honors cache_disabled parameter
            response = await self._session.request(
                method,
                url,
                params=params,
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
        await self._session.close()


class AiohttpBackend(HttpBackend):
    """aiohttp implementation of HTTP backend."""

    async def _create_session(
        self,
        cache: bool = False,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> CachedSession:
        from aiohttp_client_cache import CachedSession, SQLiteBackend

        if cache:
            path = str(self.cache_dir / "http_cache.db")
            cache_backend = SQLiteBackend(cache_name=path, expire_after=self.cache_ttl)
            return CachedSession(cache=cache_backend, headers=headers, base_url=base_url)

        # Even when not caching, we use CachedSession for consistent interface
        return CachedSession(expire_after=0, headers=headers, base_url=base_url)

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
        import aiohttp

        from anyenv.download.exceptions import RequestError, check_response

        session = await self._create_session(cache=cache)
        try:
            try:
                response = await session.request(
                    method,
                    url,
                    params=params,
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
        headers: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        cache: bool = False,
    ):
        import aiohttp

        from anyenv.download.exceptions import RequestError, ResponseError

        session = await self._create_session(cache=cache)
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
        headers: dict[str, str] | None = None,
        cache: bool = False,
    ) -> Session:
        session = await self._create_session(
            cache=cache,
            base_url=base_url,
            headers=headers,
        )
        return AiohttpSession(session, base_url)
