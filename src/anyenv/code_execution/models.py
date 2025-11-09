"""Data models for code execution environments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel


@dataclass
class ServerInfo:
    """Information about a running tool server."""

    url: str
    port: int
    tools: dict[str, Any] = field(default_factory=dict)


class ToolCallRequest(BaseModel):
    """Request model for tool calls."""

    params: dict[str, Any]


class ToolCallResponse(BaseModel):
    """Response model for tool calls."""

    result: Any = None
    error: str | None = None
    error_type: str | None = None


# Type alias for supported languages
Language = Literal["python", "javascript", "typescript"]


@dataclass
class ExecutionResult:
    """Result of code execution with metadata."""

    result: Any
    duration: float
    success: bool
    error: str | None = None
    error_type: str | None = None
    stdout: str | None = None
    stderr: str | None = None
