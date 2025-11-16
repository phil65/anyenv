"""HTTPX backend implementation for anyenv."""

from __future__ import annotations

import httpx


class JSTransport(httpx.AsyncBaseTransport):
    """JSTransport for Pyodide."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Handle an asynchronous HTTP request using the Pyodide fetch API."""
        import js  # pyright: ignore

        body = await request.aread()
        headers = dict(request.headers)
        options = {"method": request.method, "headers": headers, "body": body}
        fetch_response = await js.fetch(str(request.url), options)
        status_code = fetch_response.status
        headers = dict(fetch_response.headers)
        buffer = await fetch_response.arrayBuffer()
        content = buffer.to_bytes()
        return httpx.Response(status_code=status_code, headers=headers, content=content)
