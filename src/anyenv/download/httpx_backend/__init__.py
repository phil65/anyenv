"""HTTPX Backend (httpx2, plus legacy httpx)."""

from typing import Any

from anyenv.download.httpx_backend.js_transport import get_js_transport_class
from anyenv.download.httpx_backend.module import get_httpx_module
from anyenv.download.httpx_backend.backend import (
    Httpx2Backend,
    HttpxBackend,
    HttpxResponse,
    HttpxSession,
)


def __getattr__(name: str) -> Any:
    # `JSTransport` is built lazily on the preferred httpx flavour (httpx2 first).
    if name == "JSTransport":
        return get_js_transport_class()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "Httpx2Backend",
    "HttpxBackend",
    "HttpxResponse",
    "HttpxSession",
    "JSTransport",  # pyright: ignore[reportUnsupportedDunderAll]
    "get_httpx_module",
    "get_js_transport_class",
]
