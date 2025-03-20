"""HTTP / Download types."""

from __future__ import annotations

from collections.abc import Mapping
from typing import BinaryIO, Literal, Protocol, runtime_checkable


@runtime_checkable
class SecretStr(Protocol):
    """Protocol for secret string objects with get_secret_value() method."""

    def get_secret_value(self) -> str:
        """Get the secret value as a string."""
        ...


# Existing types
HeaderType = dict[str, str]
ParamsType = Mapping[str, str | int | float | None]
AuthType = Literal["bearer", "basic", "header", "query"]
CacheType = Literal["sqlite", "file", "memory"]
# New types for file uploads
type FileContent = str | bytes | BinaryIO
type FileType = FileContent | tuple[str, FileContent] | tuple[str, FileContent, str]
FilesType = Mapping[str, FileType]
