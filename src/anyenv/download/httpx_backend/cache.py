"""HTTP caching layer for the httpx backends, built on hishel's cache transport.

hishel stores the raw (still content-encoded) body of a response together with
its ``Content-Encoding`` header. Such an entry is only readable by a client that
supports the same encoding: an entry written by httpx2 on Python 3.14+ (which
decodes zstd via ``compression.zstd``) comes back as undecodable zstd bytes in an
environment without zstd support. hishel also only applies a TTL when an entry is
written, so a caller asking for a shorter TTL would still be served older data.

The transports here wrap hishel's ``AsyncCacheTransport``:

- ``DecodingTransport`` sits below the cache and decodes response bodies before
  they are stored, so cache entries are portable between environments. It also
  stamps each stored response with the time it was fetched.
- ``GuardTransport`` sits above the cache, passes the requested TTL to hishel
  and validates every cache hit. A hit that is older than the requested TTL,
  uses an encoding this client cannot decode, or whose body cannot be read is
  removed and fetched again instead of being returned (or raising).
"""

from __future__ import annotations

import functools
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    import hishel
    import httpx


logger = logging.getLogger(__name__)

STORED_AT_HEADER = "x-anyenv-stored-at"
"""Response header holding the UNIX time at which a cached response was fetched."""

CACHEABLE_METHODS = frozenset({"GET", "HEAD"})
_HOP_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


def cache_key(method: str, url: str) -> str:
    """Return the storage key for a request (same scheme as hishel's default)."""
    return hashlib.sha256(f"{method} {url}".encode()).hexdigest()


def _content_codings(headers: httpx.Headers) -> list[str]:
    values = headers.get_list("content-encoding", split_commas=True)
    return [v.strip().lower() for v in values if v.strip().lower() not in ("", "identity")]


@functools.cache
def get_cache_client_class(httpx_name: str, hishel_name: str) -> Callable[..., httpx.AsyncClient]:
    """Return an ``AsyncClient`` subclass for given httpx flavour that caches responses.

    Args:
        httpx_name: Module name of the httpx flavour ("httpx" or "httpx2")
        hishel_name: Module name of the matching hishel integration
    """
    import importlib

    httpx_mod: ModuleType = importlib.import_module(httpx_name)
    hishel_mod: ModuleType = importlib.import_module(hishel_name)
    decoders: dict[str, Any] = importlib.import_module(f"{httpx_name}._decoders").SUPPORTED_DECODERS

    class DecodingTransport(httpx_mod.AsyncBaseTransport):  # type: ignore[name-defined,misc]
        """Decode bodies of cacheable responses before hishel stores them."""

        def __init__(self, next_transport: httpx.AsyncBaseTransport) -> None:
            self.next_transport = next_transport

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            response = await self.next_transport.handle_async_request(request)
            if request.method not in CACHEABLE_METHODS or not response.is_success:
                return response
            if _content_codings(response.headers):
                try:
                    content = await response.aread()  # decodes according to the headers
                finally:
                    await response.aclose()
                headers = [
                    (k, v)
                    for k, v in response.headers.multi_items()
                    if k.lower() not in _HOP_HEADERS
                ]
                headers.append(("content-length", str(len(content))))
                response = httpx_mod.Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=content,
                    request=request,
                    extensions=dict(response.extensions),
                )
            response.headers[STORED_AT_HEADER] = repr(time.time())
            return response

        async def aclose(self) -> None:
            await self.next_transport.aclose()

    class GuardTransport(httpx_mod.AsyncBaseTransport):  # type: ignore[name-defined,misc]
        """Apply the requested TTL and turn unusable cache hits into cache misses."""

        def __init__(
            self,
            next_transport: httpx.AsyncBaseTransport,
            storage: hishel.AsyncBaseStorage,
            ttl: float | None,
        ) -> None:
            self.cache_transport = hishel_mod.AsyncCacheTransport(
                next_transport=DecodingTransport(next_transport), storage=storage
            )
            self.storage = storage
            self.ttl = ttl

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if request.method not in CACHEABLE_METHODS:
                return await self.cache_transport.handle_async_request(request)
            key = cache_key(request.method, str(request.url))
            overrides = dict(request.extensions.get("caching", {}))
            overrides.setdefault("key", key)
            overrides.setdefault("ttl", self.ttl)
            request.extensions = {**request.extensions, "caching": overrides}
            key = overrides["key"]

            response = await self.cache_transport.handle_async_request(request)
            if not (response.extensions.get("caching") or {}).get("from_cache"):
                return response
            if reason := await self._unusable_reason(response):
                logger.debug("Discarding cached response for %s: %s", request.url, reason)
                await response.aclose()
                await self._drop(key)
                response = await self.cache_transport.handle_async_request(request)
            return response

        async def _unusable_reason(self, response: httpx.Response) -> str | None:
            if self.ttl is not None and (stamp := response.headers.get(STORED_AT_HEADER)):
                try:
                    age = time.time() - float(stamp)
                except ValueError:
                    return f"invalid {STORED_AT_HEADER} header {stamp!r}"
                if age > self.ttl:
                    return f"older than {self.ttl}s"
            if unsupported := [c for c in _content_codings(response.headers) if c not in decoders]:
                return f"unsupported content encoding {unsupported}"
            try:
                # Make sure the stored body can be read and decoded completely.
                await response.aread()
            except Exception as exc:  # noqa: BLE001
                return f"unreadable body ({exc!r})"
            return None

        async def _drop(self, key: str) -> None:
            try:
                for entry in await self.storage.get_entries(key):
                    await self.storage.remove_entry(entry.id)
            except Exception:
                logger.debug("Could not remove cache entry %s", key, exc_info=True)

        async def aclose(self) -> None:
            await self.cache_transport.aclose()

    class CacheClient(httpx_mod.AsyncClient):  # type: ignore[name-defined,misc]
        """``AsyncClient`` whose transports (including proxy mounts) cache responses."""

        def __init__(
            self,
            *args: Any,
            storage: hishel.AsyncBaseStorage,
            ttl: float | None = None,
            **kwargs: Any,
        ) -> None:
            # Set before super().__init__, which creates the transports.
            self._anyenv_storage = storage
            self._anyenv_ttl = ttl
            super().__init__(*args, **kwargs)

        def _wrap(self, transport: httpx.AsyncBaseTransport) -> httpx.AsyncBaseTransport:
            return GuardTransport(transport, self._anyenv_storage, self._anyenv_ttl)

        def _init_transport(self, *args: Any, **kwargs: Any) -> httpx.AsyncBaseTransport:
            if kwargs.get("transport") is not None:
                return self._wrap(kwargs["transport"])
            return self._wrap(super()._init_transport(*args, **kwargs))

        def _init_proxy_transport(self, *args: Any, **kwargs: Any) -> httpx.AsyncBaseTransport:
            return self._wrap(super()._init_proxy_transport(*args, **kwargs))

    return CacheClient
