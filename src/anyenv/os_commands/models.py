"""Data models for OS command results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class FileInfo:
    """File information model."""

    name: str
    path: str
    type: Literal["file", "directory", "link"]
    size: int
    mtime: int | None = None
    timestamp: str | None = None
    permissions: str | None = None


@dataclass
class DirectoryEntry:
    """Directory entry model for detailed listings."""

    name: str
    path: str
    type: Literal["file", "directory", "link"]
    size: int
    timestamp: str | None = None
    permissions: str | None = None


@dataclass
class CommandResult:
    """Base command result model."""

    success: bool
    exit_code: int = 0
    output: str = ""
    error: str = ""


@dataclass
class ExistsResult:
    """Result for existence check commands."""

    exists: bool
    path: str


@dataclass
class CreateDirectoryResult:
    """Result for directory creation commands."""

    success: bool
    path: str
    created: bool = True


@dataclass
class RemovePathResult:
    """Result for path removal commands."""

    success: bool
    path: str
    removed: bool = True
