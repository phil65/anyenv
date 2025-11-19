"""Data models for code execution environments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ServerInfo:
    """Information about a running server."""

    url: str
    """The URL of the running server."""

    port: int
    """The port of the running server."""

    tools: dict[str, Any] = field(default_factory=dict)


Language = Literal["python", "javascript", "typescript"]


@dataclass
class ExecutionResult:
    """Result of code execution with metadata."""

    result: Any
    """The result of the code execution."""

    duration: float
    """The duration of the code execution."""

    success: bool
    """Whether the code execution was successful."""

    error: str | None = None
    """The error message if the code execution failed."""

    error_type: str | None = None
    """The type of error if the code execution failed."""

    stdout: str | None = None
    """The standard output of the code execution."""

    stderr: str | None = None
    """The standard error of the code execution."""

    exit_code: int | None = None
    """The exit code of the command execution (for command execution only)."""
