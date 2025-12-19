"""Diagnostic runner for LSP servers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import posixpath
import time
from typing import TYPE_CHECKING, Protocol

from anyenv.lsp_servers._base import DiagnosticsResult


if TYPE_CHECKING:
    from anyenv.lsp_servers._base import Diagnostic, LSPServerInfo


class CommandResult(Protocol):
    """Protocol for command execution results."""

    @property
    def stdout(self) -> str | None: ...

    @property
    def stderr(self) -> str | None: ...

    @property
    def exit_code(self) -> int | None: ...

    @property
    def duration(self) -> float: ...


@dataclass
class SimpleCommandResult:
    """Simple implementation of CommandResult."""

    stdout: str | None
    stderr: str | None
    exit_code: int | None
    duration: float


class CommandExecutor(Protocol):
    """Protocol for command execution."""

    async def __call__(self, command: str) -> CommandResult:
        """Execute a command and return the result."""
        ...


async def _default_executor(command: str) -> SimpleCommandResult:
    """Default executor using asyncio subprocess."""
    start = time.perf_counter()
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    duration = time.perf_counter() - start
    return SimpleCommandResult(
        stdout=stdout.decode() if stdout else "",
        stderr=stderr.decode() if stderr else "",
        exit_code=proc.returncode,
        duration=duration,
    )


class DiagnosticRunner:
    """Run diagnostics using CLI tools.

    Works with any command executor (local subprocess, Docker, SSH, etc.) to run
    CLI diagnostic tools and parse their output.
    """

    def __init__(self, executor: CommandExecutor | None = None) -> None:
        """Initialize with an optional command executor.

        Args:
            executor: Callable to execute commands. Defaults to local subprocess.
        """
        self._executor = executor or _default_executor
        self._servers: list[LSPServerInfo] = []

    def register(self, server: LSPServerInfo) -> None:
        """Register an LSP server for diagnostics."""
        if server.has_cli_diagnostics:
            self._servers.append(server)

    def register_defaults(self) -> None:
        """Register all default servers with CLI diagnostic support."""
        from anyenv.lsp_servers._servers import ALL_SERVERS

        for server in ALL_SERVERS:
            if server.has_cli_diagnostics:
                self.register(server)

    def get_server(self, server_id: str) -> LSPServerInfo | None:
        """Get a server by ID."""
        return next((s for s in self._servers if s.id == server_id), None)

    def get_servers_for_file(self, path: str) -> list[LSPServerInfo]:
        """Get all servers that can handle a file."""
        ext = posixpath.splitext(path)[1]
        return [s for s in self._servers if s.can_handle(ext)]

    async def run(self, server: LSPServerInfo | str, files: list[str]) -> DiagnosticsResult:
        """Run diagnostics using a specific server.

        Args:
            server: Server instance or server ID
            files: File paths to check

        Returns:
            DiagnosticsResult with parsed diagnostics
        """
        if isinstance(server, str):
            srv = self.get_server(server)
            if srv is None:
                msg = f"Server {server!r} not found"
                return DiagnosticsResult(diagnostics=[], success=False, duration=0.0, error=msg)
            server = srv

        if not server.has_cli_diagnostics:
            msg = f"Server {server.id!r} has no CLI diagnostic support"
            return DiagnosticsResult(diagnostics=[], success=False, duration=0.0, error=msg)

        command = server.build_diagnostic_command(files)
        result = await self._executor(command)
        diagnostics = server.parse_diagnostics(result.stdout or "", result.stderr or "")
        # Parsing succeeded, even if there are errors
        return DiagnosticsResult(diagnostics=diagnostics, success=True, duration=result.duration)

    async def run_all(self, files: list[str]) -> dict[str, DiagnosticsResult]:
        """Run all applicable servers on the given files.

        Args:
            files: File paths to check

        Returns:
            Dict mapping server ID to DiagnosticsResult
        """
        results: dict[str, DiagnosticsResult] = {}

        # Group files by extension
        files_by_ext: dict[str, list[str]] = {}
        for f in files:
            ext = posixpath.splitext(f)[1].lower()
            files_by_ext.setdefault(ext, []).append(f)

        # Run each applicable server
        seen_servers: set[str] = set()
        for ext, ext_files in files_by_ext.items():
            for server in self._servers:
                if server.id in seen_servers:
                    continue
                if server.can_handle(ext):
                    seen_servers.add(server.id)
                    results[server.id] = await self.run(server, ext_files)

        return results

    async def run_for_file(self, path: str) -> list[Diagnostic]:
        """Run all applicable servers on a single file.

        Args:
            path: File path to check

        Returns:
            Combined list of diagnostics from all applicable servers
        """
        all_diagnostics: list[Diagnostic] = []
        for server in self.get_servers_for_file(path):
            result = await self.run(server, [path])
            all_diagnostics.extend(result.diagnostics)

        return all_diagnostics
