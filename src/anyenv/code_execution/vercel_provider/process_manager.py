"""Vercel-specific terminal manager using detached command execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager import BaseTerminal, ProcessManagerProtocol, ProcessOutput


if TYPE_CHECKING:
    from pathlib import Path

    from vercel.sandbox import AsyncCommand, AsyncSandbox


logger = get_logger(__name__)


@dataclass
class VercelTerminal(BaseTerminal):
    """Terminal implementation for Vercel provider."""

    command_id: str | None = None
    _command: AsyncCommand | None = None
    _task: asyncio.Task[None] | None = None

    def is_running(self) -> bool:
        """Check if the terminal is still running."""
        if self._command is None:
            return False
        try:
            # Vercel commands don't seem to have a direct status check
            # We'll consider it running if we haven't gotten an exit code
            return self.get_exit_code() is None
        except Exception:  # noqa: BLE001
            return False


class VercelTerminalManager(ProcessManagerProtocol):
    """Terminal manager that uses Vercel's detached command execution."""

    def __init__(self, sandbox: AsyncSandbox) -> None:
        """Initialize with a Vercel sandbox instance."""
        self.sandbox = sandbox
        self._terminals: dict[str, VercelTerminal] = {}

    async def start_process(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        output_limit: int | None = None,
    ) -> str:
        """Create a new terminal session using Vercel's detached commands."""
        terminal_id = f"vercel_term_{uuid.uuid4().hex[:8]}"
        args = args or []

        # Create terminal object
        terminal = VercelTerminal(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=str(cwd) if cwd else None,
            env=env or {},
            output_limit=output_limit or 1048576,
        )

        # Construct full command
        full_command = [command, *args]
        cmd_str = " ".join(full_command)

        try:
            # Run detached command through Vercel
            detached_command = await self.sandbox.run_command_detached(
                cmd_str,
                cwd=str(cwd) if cwd else None,
                env=env,
            )

            terminal._command = detached_command  # noqa: SLF001
            terminal.command_id = getattr(detached_command, "id", None)

            # Store terminal
            self._terminals[terminal_id] = terminal

            # Start output collection task
            task = asyncio.create_task(self._collect_output(terminal))
            # Store task reference to avoid RUF006 warning
            terminal._task = task  # noqa: SLF001

            logger.info(
                "Started Vercel terminal %s: %s",
                terminal_id,
                cmd_str,
            )

        except Exception as e:
            logger.exception("Failed to start Vercel command: %s", cmd_str)
            terminal.add_output(f"Failed to start command: {e}\n")
            terminal.set_exit_code(1)
            self._terminals[terminal_id] = terminal

        return terminal_id

    async def _collect_output(self, terminal: VercelTerminal) -> None:
        """Collect output from Vercel command."""
        try:
            if terminal._command:  # noqa: SLF001
                # Collect stdout
                if stdout := await terminal._command.stdout():  # noqa: SLF001
                    terminal.add_output(stdout)

                # Collect stderr
                if stderr := await terminal._command.stderr():  # noqa: SLF001
                    terminal.add_output(f"STDERR: {stderr}")

                # Get exit code if available
                if hasattr(terminal._command.cmd, "exitCode"):  # noqa: SLF001
                    exit_code = terminal._command.cmd.exitCode  # noqa: SLF001
                    if exit_code is not None:
                        terminal.set_exit_code(exit_code)

        except Exception as e:
            logger.exception("Error collecting output for %s", terminal.terminal_id)
            terminal.add_output(f"Terminal error: {e}\n")
            terminal.set_exit_code(1)

    async def get_output(self, process_id: str) -> ProcessOutput:
        """Get current output from a process."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]

        # Try to update status if command exists
        if terminal._command and terminal.is_running():  # noqa: SLF001
            try:
                # Check if command has finished by trying to get it again
                assert terminal.command_id
                updated_command = await self.sandbox.get_command(terminal.command_id)
                if updated_command.cmd.exitCode is not None:
                    # Command finished, collect final output
                    if await updated_command.stdout():
                        terminal.add_output(await updated_command.stdout())
                    if await updated_command.stderr():
                        terminal.add_output(f"STDERR: {await updated_command.stderr()}")
                    terminal.set_exit_code(updated_command.cmd.exitCode)
            except Exception:  # noqa: BLE001
                pass  # Best effort

        output = terminal.get_output()
        terminal.is_running()
        exit_code = terminal.get_exit_code()

        return ProcessOutput(
            stdout=output, stderr="", combined=output, exit_code=exit_code
        )

    async def wait_for_exit(self, process_id: str) -> int:
        """Wait for process to complete."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]
        cmd = terminal._command  # noqa: SLF001
        try:
            if cmd and terminal.is_running():
                # Poll for completion
                while terminal.is_running():
                    await asyncio.sleep(0.5)
                    if terminal.command_id:
                        try:
                            updated_command = await self.sandbox.get_command(
                                terminal.command_id
                            )
                            if updated_command.cmd.exitCode is not None:
                                terminal.set_exit_code(updated_command.cmd.exitCode)
                                break
                        except Exception:  # noqa: BLE001
                            continue

                # Get final result
                result = await cmd.wait()
                terminal.set_exit_code(result.exit_code)

        except Exception:
            logger.exception("Error waiting for process %s", process_id)
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_process(self, process_id: str) -> None:
        """Kill a running process."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]

        try:
            # Vercel doesn't appear to have a direct kill command
            # We'll mark it as killed with SIGINT exit code
            if terminal.is_running():
                terminal.set_exit_code(130)  # SIGINT exit code
                logger.info(
                    "Killed Vercel process %s (no direct kill support)",
                    process_id,
                )

        except Exception:
            logger.exception("Error killing process %s", process_id)
            terminal.set_exit_code(1)

    async def release_process(self, process_id: str) -> None:
        """Release process resources."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]

        # Kill if still running
        if terminal.is_running():
            await self.kill_process(process_id)

        # Remove from tracking
        del self._terminals[process_id]
        logger.info("Released process %s", process_id)

    def list_processes(self) -> dict[str, dict[str, Any]]:
        """List all tracked terminals and their status."""
        result = {}
        for terminal_id, terminal in self._terminals.items():
            result[terminal_id] = {
                "command": terminal.command,
                "args": terminal.args,
                "cwd": str(terminal.cwd) if terminal.cwd else None,
                "created_at": terminal.created_at.isoformat(),
                "is_running": terminal.is_running(),
                "exit_code": terminal.get_exit_code(),
                "command_id": terminal.command_id,
            }
        return result
