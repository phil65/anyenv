"""HTTPX backend implementation for anyenv."""

from __future__ import annotations

import httpx


class JSTransport(httpx.AsyncBaseTransport):
    """JSTransport for Pyodide."""

    async def handle_async_request(self, request):
        """Handle an asynchronous HTTP request using the Pyodide fetch API."""
        import js  # pyright: ignore

        url = str(request.url)
        options = {
            "method": request.method,
            "headers": dict(request.headers),
            "body": await request.aread(),
        }
        fetch_response = await js.fetch(url, options)
        status_code = fetch_response.status
        headers = dict(fetch_response.headers)
        buffer = await fetch_response.arrayBuffer()
        content = buffer.to_bytes()
        return httpx.Response(status_code=status_code, headers=headers, content=content)
