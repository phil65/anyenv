"""OpenCode text sharing provider.

This implementation "fakes" OpenCode sessions by exploiting the fact that OpenCode's
share API doesn't validate session existence. The workflow is:

1. Generate random UUIDs for session, message, and part IDs
2. Call `/share_create` with the session ID to get a secret and share URL
3. Use `/share_sync` to populate the session with:
   - Session info (title, timestamps, metadata)
   - Messages (with different roles: user, assistant, system)
   - Text parts (containing the actual shared content)

The OpenCode web interface then displays this as if it were a real session.

Two sharing modes are supported:
- `share()`: Simple string sharing (single user message)
- `share_conversation()`: Structured multi-turn conversations with different roles

Note: This is not the intended use of OpenCode's API, which is designed to share
actual OpenCode sessions created via their desktop app/CLI. However, since no
authentication is required and sessions aren't validated, this works for sharing
text and conversations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING, Literal, Self
import uuid

import httpx

from anyenv.text_sharing.base import ShareResult, TextSharer


if TYPE_CHECKING:
    from anyenv.text_sharing.base import Visibility


MessageRole = Literal["user", "assistant", "system"]


@dataclass
class MessagePart:
    """A part of a message (text, code, file, etc.)."""

    type: Literal["text"]
    """Part type - currently only 'text' is supported."""

    text: str
    """Text content of the part."""


@dataclass
class Message:
    """A message in a conversation."""

    role: MessageRole
    """Role of the message sender."""

    parts: list[MessagePart] = field(default_factory=list)
    """Parts that make up the message content."""

    def __post_init__(self) -> None:
        """Ensure at least one part exists."""
        if not self.parts:
            msg = "Message must have at least one part"
            raise ValueError(msg)

    @classmethod
    def text(cls, role: MessageRole, text: str) -> Message:
        """Create a message with a single text part.

        Convenience method for creating simple text messages.

        Args:
            role: Role of the message sender
            text: Text content

        Returns:
            Message with a single text part

        Example:
            ```python
            msg = Message.text("user", "Hello!")
            # Equivalent to:
            msg = Message(role="user", parts=[MessagePart(type="text", text="Hello!")])
            ```
        """
        return cls(role=role, parts=[MessagePart(type="text", text=text)])


class OpenCodeSharer(TextSharer):
    """OpenCode text sharing service.

    Creates fake sessions by generating UUIDs and syncing content via the share API.
    OpenCode doesn't validate session existence, allowing us to create ad-hoc shares.

    Examples:
        Share a simple string:
        ```python
        async with OpenCodeSharer() as sharer:
            result = await sharer.share("Hello, World!", title="My Share")
            print(result.url)  # https://opencode.ai/s/abc12345
        ```

        Share a conversation:
        ```python
        from anyenv.text_sharing.opencode import Message

        messages = [
            Message.text("user", "What is Python?"),
            Message.text("assistant", "Python is a programming language."),
            Message.text("user", "Tell me more!"),
            Message.text("assistant", "It's great for scripting and automation."),
        ]

        async with OpenCodeSharer() as sharer:
            result = await sharer.share_conversation(
                messages,
                title="Python Discussion"
            )
            print(result.url)
        ```
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
            title: Optional title for the shared content
            syntax: Syntax highlighting hint (ignored - OpenCode handles this)
            visibility: Visibility level (ignored - OpenCode uses private shares)
            expires_in: Expiration time (ignored - OpenCode doesn't support expiration)

        Returns:
            ShareResult with OpenCode share URL
        """
        try:
            session_id = str(uuid.uuid4())
            message_id = str(uuid.uuid4())
            part_id = str(uuid.uuid4())
            current_time = int(time.time() * 1000)

            # Create share (returns secret and URL)
            resp = await self._client.post(
                f"{self.api_url}/share_create",
                json={"sessionID": session_id},
            )
            resp.raise_for_status()
            share_data = resp.json()
            secret = share_data["secret"]
            share_url = share_data["url"]

            # Sync session info
            info_key = f"session/info/{session_id}"
            info_content = {
                "id": session_id,
                "projectID": "shared-content",
                "directory": "/tmp",
                "title": title or "Shared Content",
                "version": "1.0.0",
                "time": {
                    "created": current_time,
                    "updated": current_time,
                },
            }

            resp = await self._client.post(
                f"{self.api_url}/share_sync",
                json={
                    "sessionID": session_id,
                    "secret": secret,
                    "key": info_key,
                    "content": info_content,
                },
            )
            resp.raise_for_status()

            # Sync message
            msg_key = f"session/message/{session_id}/{message_id}"
            msg_content = {
                "id": message_id,
                "sessionID": session_id,
                "role": "user",
                "time": {"created": current_time},
            }

            resp = await self._client.post(
                f"{self.api_url}/share_sync",
                json={
                    "sessionID": session_id,
                    "secret": secret,
                    "key": msg_key,
                    "content": msg_content,
                },
            )
            resp.raise_for_status()

            # Sync text part with actual content
            part_key = f"session/part/{session_id}/{message_id}/{part_id}"
            part_content = {
                "id": part_id,
                "sessionID": session_id,
                "messageID": message_id,
                "type": "text",
                "text": content,
            }

            resp = await self._client.post(
                f"{self.api_url}/share_sync",
                json={
                    "sessionID": session_id,
                    "secret": secret,
                    "key": part_key,
                    "content": part_content,
                },
            )
            resp.raise_for_status()

            # Store secret in delete_url for later deletion
            delete_url = f"{self.api_url}/share_delete#{secret}"

            return ShareResult(
                url=share_url,
                raw_url=f"{self.api_url}/share_data?id={session_id[-8:]}",
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

    async def share_conversation(
        self,
        messages: list[Message],
        *,
        title: str | None = None,
        visibility: Visibility = "unlisted",
        expires_in: int | None = None,
    ) -> ShareResult:
        """Share a structured conversation with multiple messages.

        This allows sharing AI chat sessions, multi-turn conversations,
        or any structured dialogue with different roles.

        Args:
            messages: List of messages to share (must have at least one)
            title: Optional title for the conversation
            visibility: Visibility level (ignored - OpenCode uses private shares)
            expires_in: Expiration time (ignored - OpenCode doesn't support expiration)

        Returns:
            ShareResult with OpenCode share URL

        Example:
            ```python
            messages = [
                Message(role="user", parts=[MessagePart(type="text", text="Hello!")]),
                Message(role="assistant", parts=[MessagePart(type="text", text="Hi!")]),
            ]
            result = await sharer.share_conversation(messages, title="My Chat")
            ```
        """
        if not messages:
            msg = "Must provide at least one message"
            raise ValueError(msg)

        try:
            session_id = str(uuid.uuid4())
            current_time = int(time.time() * 1000)

            # Create share
            resp = await self._client.post(
                f"{self.api_url}/share_create",
                json={"sessionID": session_id},
            )
            resp.raise_for_status()
            share_data = resp.json()
            secret = share_data["secret"]
            share_url = share_data["url"]

            # Sync session info
            info_key = f"session/info/{session_id}"
            info_content = {
                "id": session_id,
                "projectID": "shared-conversation",
                "directory": "/tmp",
                "title": title or "Shared Conversation",
                "version": "1.0.0",
                "time": {
                    "created": current_time,
                    "updated": current_time,
                },
            }

            resp = await self._client.post(
                f"{self.api_url}/share_sync",
                json={
                    "sessionID": session_id,
                    "secret": secret,
                    "key": info_key,
                    "content": info_content,
                },
            )
            resp.raise_for_status()

            # Sync each message and its parts
            for msg_idx, message in enumerate(messages):
                message_id = str(uuid.uuid4())
                msg_time = current_time + (msg_idx * 1000)  # Stagger timestamps

                # Sync message
                msg_key = f"session/message/{session_id}/{message_id}"
                msg_content = {
                    "id": message_id,
                    "sessionID": session_id,
                    "role": message.role,
                    "time": {"created": msg_time},
                }

                resp = await self._client.post(
                    f"{self.api_url}/share_sync",
                    json={
                        "sessionID": session_id,
                        "secret": secret,
                        "key": msg_key,
                        "content": msg_content,
                    },
                )
                resp.raise_for_status()

                # Sync each part
                for part in message.parts:
                    part_id = str(uuid.uuid4())
                    part_key = f"session/part/{session_id}/{message_id}/{part_id}"
                    part_content = {
                        "id": part_id,
                        "sessionID": session_id,
                        "messageID": message_id,
                        "type": part.type,
                        "text": part.text,
                    }

                    resp = await self._client.post(
                        f"{self.api_url}/share_sync",
                        json={
                            "sessionID": session_id,
                            "secret": secret,
                            "key": part_key,
                            "content": part_content,
                        },
                    )
                    resp.raise_for_status()

            # Store secret in delete_url for later deletion
            delete_url = f"{self.api_url}/share_delete#{secret}"

            return ShareResult(
                url=share_url,
                raw_url=f"{self.api_url}/share_data?id={session_id[-8:]}",
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

    async def delete_share(self, result: ShareResult) -> bool:
        """Delete a shared session.

        Args:
            result: The ShareResult containing session ID and secret

        Returns:
            True if deletion was successful
        """
        if not result.delete_url or "#" not in result.delete_url:
            return False

        # Extract secret from delete_url
        secret = result.delete_url.split("#", 1)[1]

        try:
            resp = await self._client.post(
                f"{self.api_url}/share_delete",
                json={
                    "sessionID": result.id,
                    "secret": secret,
                },
            )
            resp.raise_for_status()
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


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        """Test OpenCode sharing functionality."""
        async with OpenCodeSharer() as sharer:
            # Test simple string sharing
            print("=== Simple String Share ===")
            result = await sharer.share(
                "Hello, World!\n\nThis is a test of OpenCode sharing.",
                title="Test Share",
            )
            print(f"Share URL: {result.url}")
            print(f"Raw API URL: {result.raw_url}")
            print(f"Session ID: {result.id}")

            # Test structured conversation sharing
            print("\n=== Conversation Share ===")
            messages = [
                Message.text("user", "Can you help me with Python?"),
                Message.text(
                    "assistant",
                    "Of course! I'd be happy to help with Python. What would you like to know?",
                ),
                Message.text("user", "How do I read a file?"),
                Message.text(
                    "assistant",
                    "You can read a file using:\n\n"
                    'with open("file.txt") as f:\n'
                    "    content = f.read()",
                ),
            ]
            result2 = await sharer.share_conversation(messages, title="Python Help Conversation")
            print(f"Conversation URL: {result2.url}")
            print(f"Raw API URL: {result2.raw_url}")

    asyncio.run(main())
