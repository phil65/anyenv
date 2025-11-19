"""Beam-specific terminal manager using native process management."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import shlex
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager import BaseTerminal, ProcessManagerProtocol, ProcessOutput


if TYPE_CHECKING:
    from pathlib import Path

    from beam import SandboxInstance


logger = get_logger(__name__)


@dataclass(kw_only=True)
class BeamTerminal(BaseTerminal):
    """Represents a terminal session using Beam's process management."""

    _process: Any = None  # SandboxProcess
    _task: asyncio.Task[Any] | None = None

    def is_running(self) -> bool:
        """Check if terminal is still running."""
        if self._task:
            return not self._task.done()
        if self._process:
            # Check Beam process status
            try:
                exit_code, _ = self._process.status()
            except Exception:  # noqa: BLE001
                return False
            else:
                return exit_code < 0  # Beam uses -1 for running processes

        return False

    def get_exit_code(self) -> int | None:
        """Get the exit code if available."""
        # Try to get from Beam process first
        if self._process and self._exit_code is None:
            try:
                exit_code, _ = self._process.status()
                if exit_code >= 0:
                    self._exit_code = exit_code
            except Exception:  # noqa: BLE001
                pass
        return self._exit_code

    def set_process(self, process: Any) -> None:
        """Set the Beam process object."""
        self._process = process

    def set_task(self, task: asyncio.Task[Any]) -> None:
        """Set the asyncio task."""
        self._task = task


class BeamTerminalManager(ProcessManagerProtocol):
    """Terminal manager that uses Beam's native process management."""

    def __init__(self, sandbox_instance: SandboxInstance) -> None:
        """Initialize with a Beam sandbox instance."""
        self.sandbox_instance = sandbox_instance
        self._terminals: dict[str, BeamTerminal] = {}

    async def start_process(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        output_limit: int | None = None,
    ) -> str:
        """Create a new terminal session using Beam's process management."""
        terminal_id = f"beam_term_{uuid.uuid4().hex[:8]}"
        args = args or []
        env = env or {}

        # Build command with proper shell escaping
        full_command = shlex.join([command, *args]) if args else command

        # Create terminal
        terminal = BeamTerminal(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=str(cwd) if cwd else None,
            env=env,
            output_limit=output_limit or 1048576,
        )

        self._terminals[terminal_id] = terminal

        # Start the process using Beam's exec
        try:
            cmd_parts = shlex.split(full_command)
            if not cmd_parts:
                msg = "Empty command"
                raise ValueError(msg)  # noqa: TRY301

            # Use Beam's process.exec for direct command execution
            process = self.sandbox_instance.process.exec(*cmd_parts, cwd=cwd, env=env)
            terminal.set_process(process)

            # Start background task to collect output
            task = asyncio.create_task(self._collect_output(terminal))
            terminal.set_task(task)

            logger.info("Created Beam terminal %s: %s", terminal_id, full_command)

        except Exception as e:
            # Clean up on failure
            self._terminals.pop(terminal_id, None)
            msg = f"Failed to create Beam terminal: {e}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        else:
            return terminal_id

    async def _collect_output(self, terminal: BeamTerminal) -> None:
        """Collect output from Beam process using logs stream."""
        try:
            process = terminal._process  # noqa: SLF001
            if not process:
                return

            # Stream output from Beam process
            for line in process.logs:
                terminal.add_output(line + "\n")

            # Get final exit code
            final_exit_code = await asyncio.to_thread(process.wait)
            terminal.set_exit_code(final_exit_code)

        except Exception as e:
            logger.exception(
                "Error collecting output for Beam terminal %s", terminal.terminal_id
            )
            terminal.add_output(f"Terminal error: {e}\n")
            terminal.set_exit_code(1)

    async def get_output(self, process_id: str) -> ProcessOutput:
        """Get current output from a process."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]
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
        try:
            # Wait for the background task to complete
            if task := terminal._task:  # noqa: SLF001
                await task
            # Also wait on the Beam process directly
            if process := terminal._process:  # noqa: SLF001
                exit_code = await asyncio.to_thread(process.wait)
                terminal.set_exit_code(exit_code)

        except asyncio.CancelledError:
            terminal.set_exit_code(130)  # SIGINT exit code
        except Exception:
            logger.exception("Error waiting for process %s", process_id)
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_process(self, process_id: str) -> None:
        """Kill a running process using Beam's process management."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]
        task = terminal._task  # noqa: SLF001
        process = terminal._process  # noqa: SLF001
        try:
            # Kill the Beam process
            if process and terminal.is_running():
                await asyncio.to_thread(process.kill)
                terminal.set_exit_code(130)  # SIGINT exit code

            # Cancel the background task
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            logger.info("Killed Beam process %s", process_id)

        except Exception:
            logger.exception("Error killing process %s", process_id)
            # Still mark as killed with error exit code
            terminal.set_exit_code(1)

    async def release_process(self, process_id: str) -> None:
        """Release process resources."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]
        task = terminal._task  # noqa: SLF001
        # Kill if still running
        if terminal.is_running():
            await self.kill_process(process_id)

        # Clean up background task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Remove from tracking
        del self._terminals[process_id]
        logger.info("Released process %s", process_id)

    def list_processes(self) -> dict[str, dict[str, Any]]:
        """List all tracked terminals and their status."""
        result = {}
        for terminal_id, terminal in self._terminals.items():
            result[terminal_id] = {
                "terminal_id": terminal_id,
                "command": terminal.command,
                "args": terminal.args,
                "cwd": terminal.cwd,
                "created_at": terminal.created_at.isoformat(),
                "is_running": terminal.is_running(),
                "exit_code": terminal.get_exit_code(),
                "output_limit": terminal.output_limit,
            }
        return result

    async def get_sandbox_processes(self) -> dict[int, dict[str, Any]]:
        """Get all processes running in the Beam sandbox."""
        try:
            # Use Beam's list_processes to get all running processes
            processes = await asyncio.to_thread(
                self.sandbox_instance.process.list_processes
            )
            result = {}
            for pid, process in processes.items():
                result[pid] = {
                    "pid": process.pid,
                    "command": " ".join(process.args) if process.args else "unknown",
                    "cwd": process.cwd,
                    "env": process.env,
                    "exit_code": process.exit_code,
                    "is_running": process.exit_code < 0,
                }
        except Exception:
            logger.exception("Error listing sandbox processes")
            return {}
        else:
            return result

    async def cleanup(self) -> None:
        """Clean up all terminals."""
        logger.info("Cleaning up %s Beam terminals", len(self._terminals))
        if cleanup_tasks := [self.release_process(id_) for id_ in self._terminals]:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        logger.info("Beam terminal cleanup completed")
