"""Process management for background command execution."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager.process import RunningProcess
from anyenv.process_manager.protocol import ProcessManagerProtocol
from anyenv.processes import create_process, create_shell_process


if TYPE_CHECKING:
    from anyenv.process_manager.models import ProcessOutput


logger = get_logger(__name__)


class ProcessManager(ProcessManagerProtocol):
    """Manages background processes for an agent pool."""

    def __init__(self) -> None:
        """Initialize process manager."""
        self._processes: dict[str, RunningProcess] = {}
        self._output_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def processes(self) -> dict[str, RunningProcess]:
        """Get the running processes."""
        return self._processes

    @property
    def output_tasks(self) -> dict[str, asyncio.Task[None]]:
        """Get the output tasks."""
        return self._output_tasks

    async def start_process(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        output_limit: int | None = None,
    ) -> str:
        """Start a background process.

        Args:
            command: Command to execute. When args is None/empty, this is
                interpreted as a shell command string (supporting pipes,
                redirects, etc.). When args is provided, command is the
                program name executed directly.
            args: Command arguments. If provided, command is executed directly
                with these arguments. If None/empty, command is run through
                the shell.
            cwd: Working directory
            env: Environment variables (added to current env)
            output_limit: Maximum bytes of output to retain

        Returns:
            Process ID for tracking

        Raises:
            OSError: If process creation fails
        """
        process_id = f"proc_{uuid.uuid4().hex[:8]}"
        proc_env = dict(os.environ)
        if env:
            proc_env.update(env)
        work_dir = Path(cwd) if cwd else None
        try:
            if args:
                # Direct execution with explicit args
                process = await create_process(
                    command,
                    *args,
                    cwd=work_dir,
                    env=proc_env,
                    stdout="pipe",
                    stderr="pipe",
                )
            else:
                # Shell execution for command strings (supports pipes, redirects, etc.)
                process = await create_shell_process(
                    command,
                    cwd=work_dir,
                    env=proc_env,
                    stdout="pipe",
                    stderr="pipe",
                )
            args = args or []

            # Create tracking object
            running_proc = RunningProcess(
                process_id=process_id,
                command=command,
                args=args,
                cwd=work_dir,
                env=env or {},
                process=process,
                output_limit=output_limit,
            )
            self._processes[process_id] = running_proc
            # Start output collection task
            self._output_tasks[process_id] = asyncio.create_task(self._collect_output(running_proc))
            logger.info("Started process %s: %s %s", process_id, command, " ".join(args))
        except Exception as e:
            msg = f"Failed to start process: {command} {' '.join(args or [])}"
            logger.exception(msg, exc_info=e)
            raise OSError(msg) from e
        else:
            return process_id

    async def _collect_output(self, proc: RunningProcess) -> None:
        """Collect output from process in background."""
        try:
            stdout_task = asyncio.create_task(self._read_stream(proc.process.stdout))
            stderr_task = asyncio.create_task(self._read_stream(proc.process.stderr))
            stdout_chunks = []
            stderr_chunks = []
            stdout_done = False
            stderr_done = False
            while not (stdout_done and stderr_done):
                done, pending = await asyncio.wait(
                    [stdout_task, stderr_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.1,  # Check every 100ms
                )

                for task in done:
                    if task == stdout_task and not stdout_done:
                        chunk = task.result()
                        if chunk is None:
                            stdout_done = True
                        else:
                            stdout_chunks.append(chunk)
                            proc.add_output(stdout=chunk)
                            # Restart task for next chunk
                            stdout_task = asyncio.create_task(
                                self._read_stream(proc.process.stdout)
                            )

                    elif task == stderr_task and not stderr_done:
                        chunk = task.result()
                        if chunk is None:
                            stderr_done = True
                        else:
                            stderr_chunks.append(chunk)
                            proc.add_output(stderr=chunk)
                            # Restart task for next chunk
                            stderr_task = asyncio.create_task(
                                self._read_stream(proc.process.stderr)
                            )

            # Cancel any remaining tasks
            for task in pending:
                task.cancel()

        except Exception:
            logger.exception("Error collecting output for %s", proc.process_id)

    async def _read_stream(self, stream: asyncio.StreamReader | None) -> str | None:
        """Read a chunk from a stream."""
        if not stream:
            return None
        try:
            data = await stream.read(8192)  # Read in 8KB chunks
            return data.decode("utf-8", errors="replace") if data else None
        except Exception:  # noqa: BLE001
            return None

    async def get_output(self, process_id: str) -> ProcessOutput:
        """Get current output from a process.

        Args:
            process_id: Process identifier

        Returns:
            Current process output

        Raises:
            ValueError: If process not found
        """
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        return proc.get_output()

    async def wait_for_exit(self, process_id: str) -> int:
        """Wait for process to complete.

        Args:
            process_id: Process identifier

        Returns:
            Exit code

        Raises:
            ValueError: If process not found
        """
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        exit_code = await proc.wait_for_exit()
        if process_id in self._output_tasks:
            await self._output_tasks[process_id]

        return exit_code

    async def kill_process(self, process_id: str) -> None:
        """Kill a running process.

        Args:
            process_id: Process identifier

        Raises:
            ValueError: If process not found
        """
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        await proc.kill()
        if process_id in self._output_tasks:
            self._output_tasks[process_id].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._output_tasks[process_id]

        logger.info("Killed process %s", process_id)

    async def release_process(self, process_id: str) -> None:
        """Release resources for a process.

        Args:
            process_id: Process identifier

        Raises:
            ValueError: If process not found
        """
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)
        proc = self._processes[process_id]
        if await proc.is_running():
            await proc.kill()
        if process_id in self._output_tasks:
            self._output_tasks[process_id].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._output_tasks[process_id]
            del self._output_tasks[process_id]

        del self._processes[process_id]
        logger.info("Released process %s", process_id)

    async def list_processes(self) -> list[str]:
        """List all tracked process IDs."""
        return list(self._processes.keys())

    async def get_process_info(self, process_id: str) -> dict[str, Any]:
        """Get information about a process.

        Args:
            process_id: Process identifier

        Returns:
            Process information dict

        Raises:
            ValueError: If process not found
        """
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        return {
            "process_id": process_id,
            "command": proc.command,
            "args": proc.args,
            "cwd": str(proc.cwd) if proc.cwd else None,
            "created_at": proc.created_at.isoformat(),
            "is_running": await proc.is_running(),
            "exit_code": proc.process.returncode,
            "output_limit": proc.output_limit,
        }

    async def cleanup(self) -> None:
        """Clean up all processes."""
        logger.info("Cleaning up %s processes", len(self._processes))
        # Try graceful termination first
        termination_tasks = []
        for proc in self._processes.values():
            if await proc.is_running():
                proc.process.terminate()
                termination_tasks.append(proc.wait_for_exit())

        if termination_tasks:
            try:
                future = asyncio.gather(*termination_tasks, return_exceptions=True)
                await asyncio.wait_for(future, timeout=5.0)  # Wait up to 5 seconds
            except TimeoutError:
                msg = "Some processes didn't terminate gracefully, force killing"
                logger.warning(msg)
                # Force kill remaining processes
                for proc in self._processes.values():
                    if await proc.is_running():
                        proc.process.kill()

        if self._output_tasks:
            for task in self._output_tasks.values():
                task.cancel()
            await asyncio.gather(*self._output_tasks.values(), return_exceptions=True)

        # Clear all tracking
        self._processes.clear()
        self._output_tasks.clear()
        logger.info("Process cleanup completed")


@dataclass
class BaseTerminal:
    """Base class for terminal sessions across all providers."""

    terminal_id: str
    command: str
    args: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    output_limit: int = 1048576
    _output_buffer: list[str] = field(default_factory=list)
    _output_size: int = 0
    _truncated: bool = False
    _exit_code: int | None = None

    def add_output(self, output: str) -> None:
        """Add output to buffer, applying size limits."""
        if not output:
            return

        self._output_buffer.append(output)
        self._output_size += len(output.encode())
        # Apply truncation if limit exceeded
        if self._output_size > self.output_limit:
            self._truncate_output()

    def _truncate_output(self) -> None:
        """Truncate output from beginning to stay within limit."""
        target_size = int(self.output_limit * 0.9)  # Keep 90% of limit
        # Remove chunks from beginning until under limit
        while self._output_buffer and self._output_size > target_size:
            removed = self._output_buffer.pop(0)
            self._output_size -= len(removed.encode())
            self._truncated = True

    def get_output(self) -> str:
        """Get current buffered output."""
        output = "".join(self._output_buffer)
        if self._truncated:
            output = "(output truncated)\n" + output
        return output

    def is_running(self) -> bool:
        """Check if terminal is still running. Override in subclasses."""
        return self._exit_code is None

    def set_exit_code(self, exit_code: int) -> None:
        """Set the exit code."""
        self._exit_code = exit_code

    def get_exit_code(self) -> int | None:
        """Get the exit code if available."""
        return self._exit_code
