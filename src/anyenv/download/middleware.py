"""Header middleware system for HTTP requests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from anyenv.download.http_types import HeaderType

type HeaderMiddleware = Callable[[str, HeaderType], HeaderType]


def github_token_middleware(url: str, headers: HeaderType) -> HeaderType:
    """Inject GitHub API token from environment if available.

    Checks GH_TOKEN first, then GITHUB_TOKEN. Only injects for github.com
    and api.github.com domains if no Authorization header is already set.

    Args:
        url: The request URL
        headers: Current request headers

    Returns:
        Modified headers with Authorization if applicable.
    """
    if "Authorization" in headers:
        return headers

    # Only inject for GitHub domains
    if not any(domain in url for domain in ("github.com", "api.github.com")):
        return headers

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return headers

    return {**headers, "Authorization": f"Bearer {token}"}


class HeaderMiddlewareRegistry:
    """Registry for header middlewares applied to all requests."""

    def __init__(self) -> None:
        self._middlewares: list[HeaderMiddleware] = []

    def add(self, middleware: HeaderMiddleware) -> None:
        """Add a middleware to the registry.

        Args:
            middleware: Callable taking (url, headers) and returning modified headers.
        """
        if middleware not in self._middlewares:
            self._middlewares.append(middleware)

    def remove(self, middleware: HeaderMiddleware) -> None:
        """Remove a middleware from the registry.

        Args:
            middleware: The middleware to remove.
        """
        if middleware in self._middlewares:
            self._middlewares.remove(middleware)

    def clear(self) -> None:
        """Remove all middlewares from the registry."""
        self._middlewares.clear()

    def apply(self, url: str, headers: HeaderType | None) -> HeaderType:
        """Apply all middlewares to headers.

        Args:
            url: The request URL
            headers: Initial headers (can be None)

        Returns:
            Headers after all middlewares have been applied.
        """
        result = dict(headers) if headers else {}
        for middleware in self._middlewares:
            result = middleware(url, result)
        return result

    @property
    def middlewares(self) -> list[HeaderMiddleware]:
        """Return a copy of the current middleware list."""
        return list(self._middlewares)


# Global registry instance with GitHub middleware enabled by default
header_middlewares = HeaderMiddlewareRegistry()
header_middlewares.add(github_token_middleware)
