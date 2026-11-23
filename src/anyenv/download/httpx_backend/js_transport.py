"""Pyodide fetch-based transport for the httpx backends."""

from __future__ import annotations

import functools
from typing import Any

from anyenv.download.httpx_backend.module import get_httpx_module


@functools.cache
def get_js_transport_class(httpx_name: str | None = None) -> type[Any]:
    """Return a Pyodide fetch transport class for given httpx flavour.

    Args:
        httpx_name: Module name of the httpx flavour ("httpx2" or "httpx").
                    Defaults to httpx2 if installed, else httpx.
    """
    httpx_mod = get_httpx_module(httpx_name)

    class JSTransport(httpx_mod.AsyncBaseTransport):  # type: ignore[name-defined,misc]
        """JSTransport for Pyodide."""

        async def handle_async_request(self, request: Any) -> Any:
            """Handle an asynchronous HTTP request using the Pyodide fetch API."""
            import js  # type: ignore[import-not-found]

            body = await request.aread()
            headers = dict(request.headers)
            options = {"method": request.method, "headers": headers, "body": body}
            fetch_response = await js.fetch(str(request.url), options)
            status_code = fetch_response.status
            headers = dict(fetch_response.headers)
            buffer = await fetch_response.arrayBuffer()
            content = buffer.to_bytes()
            return httpx_mod.Response(status_code=status_code, headers=headers, content=content)

    JSTransport.__module__ = __name__
    return JSTransport


def __getattr__(name: str) -> Any:
    # `JSTransport` is resolved lazily so importing this module needs no httpx flavour.
    if name == "JSTransport":
        return get_js_transport_class()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
