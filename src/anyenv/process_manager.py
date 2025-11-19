"""Process management for background command execution."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
import uuid

from anyenv.log import get_logger
from anyenv.processes import create_process


if TYPE_CHECKING:
    from anyenv.code_execution.base import ExecutionEnvironment


logger = get_logger(__name__)


class TerminalManagerProtocol(Protocol):
    """Protocol for managing terminal sessions."""

    async def create_terminal(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Create a new terminal session.

        Returns:
            Terminal ID for tracking
        """
        ...

    async def get_command_output(self, terminal_id: str) -> tuple[str, bool, int | None]:
        """Get current output from terminal.

        Returns:
            Tuple of (output, is_running, exit_code)
        """
        ...

    async def wait_for_terminal_exit(self, terminal_id: str) -> int:
        """Wait for terminal to complete.

        Returns:
            Exit code
        """
        ...

    async def kill_terminal(self, terminal_id: str) -> None:
        """Kill a running terminal."""
        ...

    async def release_terminal(self, terminal_id: str) -> None:
        """Release terminal resources."""
        ...


@dataclass
class ProcessOutput:
    """Output from a running process."""

    stdout: str
    stderr: str
    combined: str
    truncated: bool = False
    exit_code: int | None = None
    signal: str | None = None


@dataclass
class RunningProcess:
    """Represents a running background process."""

    process_id: str
    command: str
    args: list[str]
    cwd: Path | None
    env: dict[str, str]
    process: asyncio.subprocess.Process
    created_at: datetime = field(default_factory=datetime.now)
    output_limit: int | None = None
    _stdout_buffer: list[str] = field(default_factory=list)
    _stderr_buffer: list[str] = field(default_factory=list)
    _output_size: int = 0
    _truncated: bool = False

    def add_output(self, stdout: str = "", stderr: str = "") -> None:
        """Add output to buffers, applying size limits."""
        if stdout:
            self._stdout_buffer.append(stdout)
            self._output_size += len(stdout.encode())
        if stderr:
            self._stderr_buffer.append(stderr)
            self._output_size += len(stderr.encode())

        # Apply truncation if limit exceeded
        if self.output_limit and self._output_size > self.output_limit:
            self._truncate_output()
            self._truncated = True

    def _truncate_output(self) -> None:
        """Truncate output from beginning to stay within limit."""
        if not self.output_limit:
            return

        # Combine all output to measure total size
        all_stdout = "".join(self._stdout_buffer)
        all_stderr = "".join(self._stderr_buffer)

        # Calculate how much to keep
        target_size = int(self.output_limit * 0.9)  # Keep 90% of limit

        # Truncate stdout first, then stderr if needed
        if len(all_stdout.encode()) > target_size:
            # Find character boundary for truncation
            truncated_stdout = all_stdout[-target_size:].lstrip()
            self._stdout_buffer = [truncated_stdout]
            self._stderr_buffer = [all_stderr]
        else:
            remaining = target_size - len(all_stdout.encode())
            truncated_stderr = all_stderr[-remaining:].lstrip()
            self._stdout_buffer = [all_stdout]
            self._stderr_buffer = [truncated_stderr]

        # Update size counter
        self._output_size = sum(
            len(chunk.encode()) for chunk in self._stdout_buffer + self._stderr_buffer
        )

    def get_output(self) -> ProcessOutput:
        """Get current process output."""
        stdout = "".join(self._stdout_buffer)
        stderr = "".join(self._stderr_buffer)
        combined = stdout + stderr

        # Check if process has exited
        exit_code = self.process.returncode
        signal = None  # TODO: Extract signal info if available

        return ProcessOutput(
            stdout=stdout,
            stderr=stderr,
            combined=combined,
            truncated=self._truncated,
            exit_code=exit_code,
            signal=signal,
        )

    async def is_running(self) -> bool:
        """Check if process is still running."""
        return self.process.returncode is None

    async def wait(self) -> int:
        """Wait for process to complete and return exit code."""
        return await self.process.wait()

    async def kill(self) -> None:
        """Terminate the process."""
        if await self.is_running():
            try:
                self.process.terminate()
                # Give it a moment to terminate gracefully
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except TimeoutError:
                    # Force kill if it doesn't terminate
                    self.process.kill()
                    await self.process.wait()
            except ProcessLookupError:
                # Process already dead
                pass


class ProcessManager(TerminalManagerProtocol):
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
            command: Command to execute
            args: Command arguments
            cwd: Working directory
            env: Environment variables (added to current env)
            output_limit: Maximum bytes of output to retain

        Returns:
            Process ID for tracking

        Raises:
            OSError: If process creation fails
        """
        process_id = f"proc_{uuid.uuid4().hex[:8]}"
        args = args or []

        # Prepare environment
        proc_env = dict(os.environ)
        if env:
            proc_env.update(env)

        # Convert cwd to Path if provided
        work_dir = Path(cwd) if cwd else None

        try:
            # Start process
            process = await create_process(
                command,
                *args,
                cwd=work_dir,
                env=proc_env,
                stdout="pipe",
                stderr="pipe",
            )

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
            self._output_tasks[process_id] = asyncio.create_task(
                self._collect_output(running_proc)
            )

            logger.info("Started process %s: %s %s", process_id, command, " ".join(args))
        except Exception as e:
            msg = f"Failed to start process: {command} {' '.join(args)}"
            logger.exception(msg, exc_info=e)
            raise OSError(msg) from e
        else:
            return process_id

    async def _collect_output(self, proc: RunningProcess) -> None:
        """Collect output from process in background."""
        try:
            # Read output streams concurrently
            stdout_task = asyncio.create_task(self._read_stream(proc.process.stdout))
            stderr_task = asyncio.create_task(self._read_stream(proc.process.stderr))

            stdout_chunks = []
            stderr_chunks = []

            # Collect output until both streams close
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
        exit_code = await proc.wait()

        # Wait for output collection to finish
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

        # Cancel output collection task
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

        # Kill if still running
        proc = self._processes[process_id]
        if await proc.is_running():
            await proc.kill()

        # Clean up tasks
        if process_id in self._output_tasks:
            self._output_tasks[process_id].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._output_tasks[process_id]
            del self._output_tasks[process_id]

        # Remove from tracking
        del self._processes[process_id]
        logger.info("Released process %s", process_id)

    def list_processes(self) -> list[str]:
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
                termination_tasks.append(proc.wait())

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
    cwd: str | None
    env: dict[str, str]
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


@dataclass
class TerminalTask(BaseTerminal):
    """Represents a running terminal task for the generic implementation."""

    task: asyncio.Task[Any] | None = field(default=None)

    def is_running(self) -> bool:
        """Check if task is still running."""
        return self.task is not None and not self.task.done()


class EnvironmentTerminalManager:
    """Terminal manager that uses ExecutionEnvironment for command execution."""

    def __init__(self, env: ExecutionEnvironment) -> None:
        """Initialize with an execution environment."""
        self.env = env
        self._terminals: dict[str, TerminalTask] = {}

    async def create_terminal(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Create a new terminal session."""
        terminal_id = f"term_{uuid.uuid4().hex[:8]}"
        args = args or []
        env = env or {}

        # Build full command with proper shell escaping
        if args:
            # Use shell-safe command construction
            import shlex

            full_command = shlex.join([command, *args])
        else:
            full_command = command

        # Create terminal task
        terminal = TerminalTask(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            task=asyncio.create_task(self._run_terminal(terminal_id, full_command)),
            output_limit=output_byte_limit,
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

    async def get_command_output(self, terminal_id: str) -> tuple[str, bool, int | None]:
        """Get current output from terminal."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]
        output = terminal.get_output()
        is_running = terminal.is_running()
        exit_code = terminal.get_exit_code()

        return output, is_running, exit_code

    async def wait_for_terminal_exit(self, terminal_id: str) -> int:
        """Wait for terminal to complete."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        try:
            assert terminal.task
            await terminal.task
        except asyncio.CancelledError:
            terminal.set_exit_code(130)  # SIGINT exit code
        except Exception:  # noqa: BLE001
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_terminal(self, terminal_id: str) -> None:
        """Kill a running terminal."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        if terminal.is_running():
            if terminal.task:
                terminal.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await terminal.task
            terminal.set_exit_code(130)  # SIGINT exit code

        logger.info("Killed terminal %s", terminal_id)

    async def release_terminal(self, terminal_id: str) -> None:
        """Release terminal resources."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        # Kill if still running
        if terminal.is_running():
            await self.kill_terminal(terminal_id)

        # Cancel task if it exists
        if terminal.task and not terminal.task.done():
            terminal.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await terminal.task

        # Remove from tracking
        del self._terminals[terminal_id]
        logger.info("Released terminal %s", terminal_id)
