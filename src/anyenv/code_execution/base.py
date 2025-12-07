"""Base execution environment interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType
    from typing import Any

    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import ExecutionResult, ServerInfo
    from anyenv.process_manager import ProcessManagerProtocol


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
        from anyenv.lsp_servers import DiagnosticRunner

        self.lifespan_handler = lifespan_handler
        self.server_info: ServerInfo | None = None
        self.dependencies = dependencies or []
        self._process_manager: ProcessManagerProtocol | None = None
        self.lsp_servers = DiagnosticRunner(self)
        self.lsp_servers.register_defaults()

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
    def process_manager(self) -> ProcessManagerProtocol:
        """Get the process manager for this execution environment."""
        if self._process_manager is None:
            from anyenv.code_execution.process_manager import EnvironmentTerminalManager

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

    async def set_file_content(self, path: str, content: str | bytes) -> None:
        """Set file content in the filesystem.

        Args:
            path: Path in the filesystem
            content: File content (str or bytes)
        """
        if isinstance(content, str):
            content = content.encode()
        await self.get_fs()._pipe_file(path, content)  # noqa: SLF001

    async def get_file_content(self, path: str) -> bytes:
        """Get file content from the filesystem.

        Args:
            path: Path in the filesystem

        Returns:
            File content as bytes
        """
        return await self.get_fs()._cat_file(path)  # type: ignore[no-any-return] # noqa: SLF001

    @abstractmethod
    def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events (required).

        Args:
            code: Code to execute

        Yields:
            ExecutionEvent objects as they occur
        """
        ...

    @abstractmethod
    def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a terminal command and stream events (required).

        Args:
            command: Terminal command to execute

        Yields:
            ExecutionEvent objects as they occur
        """
        ...

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line.

        Default implementation delegates to stream_code() and filters OutputEvents.

        Args:
            code: Code to execute

        Yields:
            Lines of output as they are produced
        """
        from anyenv.code_execution.events import OutputEvent

        async for event in self.stream_code(code):
            if isinstance(event, OutputEvent):
                yield event.data

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
        """Execute a terminal command and stream output line by line.

        Default implementation delegates to stream_command() and filters OutputEvents.

        Args:
            command: Terminal command to execute

        Yields:
            Lines of output as they are produced
        """
        from anyenv.code_execution.events import OutputEvent

        async for event in self.stream_command(command):
            if isinstance(event, OutputEvent):
                yield event.data

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
    async def execute_script_stream(cls, script_content: str, **kwargs: Any) -> AsyncIterator[str]:
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
