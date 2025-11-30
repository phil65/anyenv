"""Event types for streaming code execution."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BaseExecutionEvent(BaseModel):
    """Base event for all execution events."""

    timestamp: datetime = Field(default_factory=datetime.now)
    process_id: str | None = None


class ProcessStartedEvent(BaseExecutionEvent):
    """Process has started executing."""

    event_type: Literal["started"] = "started"
    command: str
    pid: int | None = None


class OutputEvent(BaseExecutionEvent):
    """Output data from process."""

    event_type: Literal["output"] = "output"
    data: str
    stream: Literal["stdout", "stderr", "combined"]


class ProcessCompletedEvent(BaseExecutionEvent):
    """Process completed successfully."""

    event_type: Literal["completed"] = "completed"
    exit_code: int
    duration: float | None = None


class ProcessErrorEvent(BaseExecutionEvent):
    """Process encountered an error."""

    event_type: Literal["error"] = "error"
    error: str
    error_type: str
    exit_code: int | None = None

    @classmethod
    def failed(
        cls, exception: Exception, process_id: str, exit_code: int | None = None
    ) -> ProcessErrorEvent:
        """Create a ProcessErrorEvent from an exception."""
        return cls(
            error=str(exception),
            error_type=type(exception).__name__,
            process_id=process_id,
            exit_code=exit_code,
        )


# Discriminated union of all execution events
ExecutionEvent = ProcessStartedEvent | OutputEvent | ProcessCompletedEvent | ProcessErrorEvent
