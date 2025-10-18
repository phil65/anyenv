"""Base execution environment interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.models import ExecutionResult, ServerInfo


class ExecutionEnvironment(ABC):
    """Abstract base class for code execution environments."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        **kwargs,
    ):
        """Initialize execution environment with optional lifespan handler.

        Args:
            lifespan_handler: Optional async context manager for tool server
            **kwargs: Additional keyword arguments for specific providers
        """
        self.lifespan_handler = lifespan_handler
        self.server_info: ServerInfo | None = None

    async def __aenter__(self) -> Self:
        """Setup environment (start server, spawn process, etc.)."""
        # Start tool server if provided
        if self.lifespan_handler:
            self.server_info = await self.lifespan_handler.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup (stop server, kill process, etc.)."""
        # Cleanup server if provided
        if self.lifespan_handler:
            await self.lifespan_handler.__aexit__(exc_type, exc_val, exc_tb)

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

    @abstractmethod
    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command and return result with metadata.

        Args:
            command: Terminal command to execute

        Returns:
            ExecutionResult with command output and metadata
        """
        ...

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute a terminal command and stream output line by line (optional).

        Not all execution environments support streaming commands.
        Default implementation raises NotImplementedError.

        Args:
            command: Terminal command to execute

        Yields:
            Lines of output as they are produced

        Raises:
            NotImplementedError: If command streaming is not supported
        """
        msg = f"{self.__class__.__name__} does not support command streaming"
        raise NotImplementedError(msg)
        yield
