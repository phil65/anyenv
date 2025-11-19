"""Misc process-related models."""

from __future__ import annotations

from dataclasses import dataclass

from anyenv.log import get_logger


logger = get_logger(__name__)


@dataclass
class ProcessOutput:
    """Output from a running process."""

    stdout: str
    stderr: str
    combined: str
    truncated: bool = False
    exit_code: int | None = None
    signal: str | None = None
