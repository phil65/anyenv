"""OpenCode text sharing provider."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self

import httpx

from anyenv.text_sharing.base import ShareResult, TextSharer


if TYPE_CHECKING:
    from anyenv.text_sharing.base import Visibility


class OpenCodeSharer(TextSharer):
    """OpenCode text sharing service.

    Shares content via OpenCode's session sharing API.
    Creates a temporary session and shares the content as a message.
    """

    def __init__(
        self,
        *,
        api_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize OpenCode sharer.

        Args:
            api_url: OpenCode API URL (defaults to production)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url or "https://api.opencode.ai"
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        """Name of the sharing service."""
        return "OpenCode"

    async def share(
        self,
        content: str,
        *,
        title: str | None = None,
        syntax: str | None = None,
        visibility: Visibility = "unlisted",
        expires_in: int | None = None,
    ) -> ShareResult:
        """Share text content via OpenCode.

        Args:
            content: The text content to share
            title: Optional title (used as session title)
            syntax: Syntax highlighting hint (ignored - OpenCode handles this)
            visibility: Visibility level (ignored - OpenCode uses private shares)
            expires_in: Expiration time (ignored - OpenCode doesn't support expiration)

        Returns:
            ShareResult with OpenCode share URL
        """
        try:
            # Step 1: Create a temporary session with the content
            session_data = {
                "title": title or "Shared Content",
                "content": content,
                "language": syntax or "text",
            }

            # Create session (this is a simplified version - real OpenCode API might differ)
            session_response = await self._client.post(
                f"{self.api_url}/session/create",
                json=session_data,
            )
            session_response.raise_for_status()
            session_info = session_response.json()
            session_id = session_info["sessionID"]

            # Step 2: Create a share for the session
            share_response = await self._client.post(
                f"{self.api_url}/share_create",
                json={"sessionID": session_id},
            )
            share_response.raise_for_status()
            share_data = share_response.json()

            share_url = share_data["url"]
            secret = share_data.get("secret")

            # Construct URLs
            delete_url = None
            if secret:
                delete_url = f"{self.api_url}/share_delete?sessionID={session_id}&secret={secret}"

            return ShareResult(
                url=share_url,
                raw_url=None,  # OpenCode doesn't provide raw URLs
                delete_url=delete_url,
                id=session_id,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:  # noqa: PLR2004
                msg = "OpenCode API endpoint not found - service may be unavailable"
                raise RuntimeError(msg) from e
            if e.response.status_code == 429:  # noqa: PLR2004
                msg = "Rate limited by OpenCode API"
                raise RuntimeError(msg) from e
            msg = f"OpenCode API error (HTTP {e.response.status_code}): {e.response.text}"
            raise RuntimeError(msg) from e
        except httpx.RequestError as e:
            msg = f"Failed to connect to OpenCode API: {e}"
            raise RuntimeError(msg) from e
        except (KeyError, json.JSONDecodeError) as e:
            msg = f"Invalid response from OpenCode API: {e}"
            raise RuntimeError(msg) from e

    async def delete_share(self, session_id: str, secret: str) -> bool:
        """Delete a shared session.

        Args:
            session_id: The session ID to delete
            secret: The secret key for deletion

        Returns:
            True if deletion was successful
        """
        try:
            response = await self._client.post(
                f"{self.api_url}/share_delete",
                json={"sessionID": session_id, "secret": secret},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        else:
            return True

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
