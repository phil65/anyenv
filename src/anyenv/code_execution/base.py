"""Base execution environment interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyenv.code_execution.models import ExecutionResult


class ExecutionEnvironment(ABC):
    """Abstract base class for code execution environments."""

    @abstractmethod
    async def __aenter__(self) -> ExecutionEnvironment:
        """Setup environment (start server, spawn process, etc.)."""
        ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup (stop server, kill process, etc.)."""
        ...

    @abstractmethod
    async def execute(self, code: str) -> ExecutionResult:
        """Execute code and return result with metadata."""
        ...

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line (optional).

        Not all execution environments support streaming.
        Default implementation raises NotImplementedError.

        Args:
            code: Code to execute

        Yields:
            Lines of output as they are produced

        Raises:
            NotImplementedError: If streaming is not supported
        """
        msg = f"{self.__class__.__name__} does not support streaming"
        raise NotImplementedError(msg)
        yield
