"""Process management for background command execution."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
import shlex
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager.models import ProcessOutput
from anyenv.process_manager.process_manager import BaseTerminal
from anyenv.process_manager.protocol import ProcessManagerProtocol


if TYPE_CHECKING:
    from pathlib import Path

    from anyenv.code_execution.base import ExecutionEnvironment


logger = get_logger(__name__)


@dataclass
class TerminalTask(BaseTerminal):
    """Represents a running terminal task for the generic implementation."""

    task: asyncio.Task[Any] | None = field(default=None)

    def is_running(self) -> bool:
        """Check if task is still running."""
        return self.task is not None and not self.task.done()


class EnvironmentTerminalManager(ProcessManagerProtocol):
    """Terminal manager that uses ExecutionEnvironment for command execution."""

    def __init__(self, env: ExecutionEnvironment) -> None:
        """Initialize with an execution environment."""
        self.env = env
        self._terminals: dict[str, TerminalTask] = {}

    async def start_process(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        output_limit: int | None = None,
    ) -> str:
        """Start a background process."""
        terminal_id = f"proc_{uuid.uuid4().hex[:8]}"
        args = args or []
        env = env or {}
        full_command = shlex.join([command, *args]) if args else command
        terminal = TerminalTask(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=str(cwd) if cwd else None,
            env=env,
            task=asyncio.create_task(self._run_terminal(terminal_id, full_command)),
            output_limit=output_limit or 1048576,
        )
        self._terminals[terminal_id] = terminal
        logger.info("Created terminal %s: %s", terminal_id, full_command)
        return terminal_id

    async def _run_terminal(self, terminal_id: str, command: str) -> None:
        """Run terminal command in background."""
        terminal = self._terminals[terminal_id]
        try:
            result = await self.env.execute_command(command)
            if result.stdout:
                terminal.add_output(result.stdout)
            if result.stderr:
                terminal.add_output(result.stderr)
            # Use actual exit code if available, otherwise infer from success
            if result.exit_code is not None:
                terminal.set_exit_code(result.exit_code)
            else:
                terminal.set_exit_code(0 if result.success else 1)

        except Exception as e:
            terminal.add_output(f"Terminal error: {e}\n")
            terminal.set_exit_code(1)
            logger.exception("Error in terminal %s", terminal_id)

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
            assert terminal.task
            await terminal.task
        except asyncio.CancelledError:
            terminal.set_exit_code(130)  # SIGINT exit code
        except Exception:  # noqa: BLE001
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_process(self, process_id: str) -> None:
        """Kill a running process."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[process_id]
        if terminal.is_running():
            if terminal.task:
                terminal.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await terminal.task
            terminal.set_exit_code(130)  # SIGINT exit code

        logger.info("Killed process %s", process_id)

    async def release_process(self, process_id: str) -> None:
        """Release process resources."""
        if process_id not in self._terminals:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)
        terminal = self._terminals[process_id]
        if terminal.is_running():
            await self.kill_process(process_id)
        if terminal.task and not terminal.task.done():
            terminal.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await terminal.task
        del self._terminals[process_id]
        logger.info("Released process %s", process_id)
