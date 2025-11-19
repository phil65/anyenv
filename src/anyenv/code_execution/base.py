"""Base execution environment interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType
    from typing import Any

    from fsspec.asyn import AsyncFileSystem

    from anyenv.code_execution.models import ExecutionResult, ServerInfo
    from anyenv.process_manager import TerminalManagerProtocol


class ExecutionEnvironment(ABC):
    """Abstract base class for code execution environments."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize execution environment with optional lifespan handler.

        Args:
            lifespan_handler: Optional async context manager for tool server
            dependencies: Optional list of dependencies to install
            **kwargs: Additional keyword arguments for specific providers
        """
        self.lifespan_handler = lifespan_handler
        self.server_info: ServerInfo | None = None
        self.dependencies = dependencies or []
        self._process_manager: TerminalManagerProtocol | None = None

    async def __aenter__(self) -> Self:
        """Setup environment (start server, spawn process, etc.)."""
        # Start tool server if provided
        if self.lifespan_handler:
            self.server_info = await self.lifespan_handler.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup (stop server, kill process, etc.)."""
        # Cleanup server if provided
        if self.lifespan_handler:
            await self.lifespan_handler.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def process_manager(self) -> TerminalManagerProtocol:
        """Get the process manager for this execution environment."""
        if self._process_manager is None:
            from anyenv.process_manager import EnvironmentTerminalManager

            self._process_manager = EnvironmentTerminalManager(self)
        return self._process_manager

    @abstractmethod
    async def execute(self, code: str) -> ExecutionResult:
        """Execute code and return result with metadata."""
        ...

    def get_fs(self) -> AsyncFileSystem:
        """Return a MicrosandboxFS instance for the sandbox."""
        msg = "VFS is not supported"
        raise NotImplementedError(msg)

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

    @classmethod
    async def execute_script(cls, script_content: str, **kwargs: Any) -> ExecutionResult:
        """Execute a PEP 723 script with automatic dependency management.

        Creates a new execution environment configured for the script's dependencies.

        Args:
            script_content: Python source code with PEP 723 metadata
            **kwargs: Additional keyword arguments for the execution environment

        Returns:
            ExecutionResult with script output and metadata

        Raises:
            ScriptError: If the script metadata is invalid or malformed
        """
        from anyenv.code_execution.pep723 import parse_script_metadata

        metadata = parse_script_metadata(script_content)
        async with cls(dependencies=metadata.dependencies, **kwargs) as env:
            return await env.execute(script_content)

    @classmethod
    async def execute_script_stream(
        cls, script_content: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        """Execute a PEP 723 script and stream output with dependency management.

        Creates a new execution environment configured for the script's dependencies.

        Args:
            script_content: Python source code with PEP 723 metadata
            **kwargs: Additional keyword arguments for the execution environment

        Yields:
            Lines of output as they are produced

        Raises:
            ScriptError: If the script metadata is invalid or malformed
        """
        from anyenv.code_execution.pep723 import parse_script_metadata

        metadata = parse_script_metadata(script_content)
        async with cls(dependencies=metadata.dependencies, **kwargs) as env:
            async for line in env.execute_stream(script_content):
                yield line
