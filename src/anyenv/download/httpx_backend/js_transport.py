"""Pyodide fetch-based transport for httpx (used when running under Pyodide)."""

import functools
from typing import Any

from anyenv.download.httpx_backend.module import get_httpx_module


# The browser decodes bodies itself and computes lengths: these response headers
# describe the body as it was sent, not as fetch() hands it over.
_STALE_RESPONSE_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})
_BODYLESS_METHODS = frozenset({"GET", "HEAD"})


def _request_timeout(request: Any) -> float | None:
    """Return a fetch timeout in seconds from httpx request extensions, if set."""
    timeout = request.extensions.get("timeout")
    if isinstance(timeout, dict):
        values = [v for v in timeout.values() if isinstance(v, (int, float)) and v >= 0]
        return float(min(values)) if values else None
    if isinstance(timeout, (int, float)) and timeout >= 0:
        return float(timeout)
    return None


@functools.cache
def get_js_transport_class(httpx_name: str | None = None) -> type[Any]:
    """Return a Pyodide fetch transport class for given httpx flavour.

    Targets Pyodide 314.x (Python 3.14), where ``to_js`` already turns dicts into plain JS
    objects (checked in a browser against 314.0.8); ``dict_converter=js.Object.fromEntries``
    is kept explicitly because ``fetch()`` ignores options passed as a JS ``Map``.

    Args:
        httpx_name: Module name of the httpx flavour ("httpx2" or "httpx").
                    Defaults to httpx2 if installed, else httpx.
    """
    httpx_mod = get_httpx_module(httpx_name)

    class JSTransport(httpx_mod.AsyncBaseTransport):  # type: ignore[name-defined,misc]
        """Send httpx requests through the browser's ``fetch``."""

        async def handle_async_request(self, request: Any) -> Any:
            """Handle an asynchronous HTTP request using the browser fetch API."""
            import js  # type: ignore[import-not-found]
            from pyodide.ffi import to_js  # type: ignore[import-not-found]

            body = await request.aread()
            options: dict[str, Any] = {
                "method": request.method,
                "headers": dict(request.headers),
                "mode": "cors",
                "redirect": "follow",
            }
            if body and request.method.upper() not in _BODYLESS_METHODS:
                options["body"] = body
            if (
                (timeout := _request_timeout(request)) is not None
                and (abort_signal := getattr(js, "AbortSignal", None)) is not None
                and hasattr(abort_signal, "timeout")
            ):
                options["signal"] = abort_signal.timeout(round(timeout * 1000))
            try:
                fetch_response = await js.fetch(
                    str(request.url), to_js(options, dict_converter=js.Object.fromEntries)
                )
                buffer = await fetch_response.arrayBuffer()
            except Exception as exc:  # JsException: network error, CORS, timeout, abort
                if getattr(exc, "name", None) == "TimeoutError":
                    raise httpx_mod.TimeoutException(str(exc), request=request) from exc
                raise httpx_mod.ConnectError(str(exc), request=request) from exc
            headers = [
                (str(k), str(v))
                for k, v in fetch_response.headers.entries()
                if str(k).lower() not in _STALE_RESPONSE_HEADERS
            ]
            extensions: dict[str, Any] = {}
            if status_text := getattr(fetch_response, "statusText", ""):
                extensions["reason_phrase"] = str(status_text).encode("ascii", errors="ignore")
            return httpx_mod.Response(
                status_code=fetch_response.status,
                headers=headers,
                content=buffer.to_bytes(),
                request=request,
                extensions=extensions,
            )

    JSTransport.__module__ = __name__
    return JSTransport


def __getattr__(name: str) -> Any:
    # `JSTransport` is resolved lazily so importing this module needs no httpx flavour.
    if name == "JSTransport":
        return get_js_transport_class()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
