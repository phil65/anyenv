"""HTTP / Download types."""

from __future__ import annotations

from collections.abc import Mapping
from typing import BinaryIO


# Existing types
HeaderType = dict[str, str]
ParamsType = Mapping[str, str | int | float | None]

# New types for file uploads
type FileContent = str | bytes | BinaryIO
type FileType = FileContent | tuple[str, FileContent] | tuple[str, FileContent, str]
FilesType = Mapping[str, FileType]
