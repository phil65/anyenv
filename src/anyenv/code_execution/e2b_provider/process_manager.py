"""E2B-specific terminal manager using native process management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager import BaseTerminal, TerminalManagerProtocol


if TYPE_CHECKING:
    from e2b import AsyncSandbox
    from e2b.sandbox_async.commands.command_handle import AsyncCommandHandle


logger = get_logger(__name__)


@dataclass
class E2BTerminal(BaseTerminal):
    """Represents a terminal session using E2B's process management."""

    pid: int | None = None
    _handle: AsyncCommandHandle | None = None

    def is_running(self) -> bool:
        """Check if terminal is still running."""
        if self._exit_code is not None:
            return False
        if self._handle:
            # Check if handle has exit_code property (None means still running)
            return self._handle.exit_code is None
        return False

    def get_exit_code(self) -> int | None:
        """Get the exit code if available."""
        if self._exit_code is not None:
            return self._exit_code
        if self._handle and self._handle.exit_code is not None:
            # Get exit code from handle if available
            self._exit_code = self._handle.exit_code
            return self._exit_code
        return None

    def set_handle(self, handle: AsyncCommandHandle) -> None:
        """Set the E2B command handle."""
        self._handle = handle
        self.pid = handle.pid


class E2BTerminalManager(TerminalManagerProtocol):
    """Terminal manager that uses E2B's native process management."""

    def __init__(self, sandbox: AsyncSandbox) -> None:
        """Initialize with an E2B sandbox instance."""
        self.sandbox = sandbox
        self._terminals: dict[str, E2BTerminal] = {}

    async def create_terminal(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Create a new terminal session using E2B's background commands."""
        terminal_id = f"e2b_term_{uuid.uuid4().hex[:8]}"
        args = args or []
        env = env or {}

        # Build full command
        full_command = f"{command} {' '.join(args)}" if args else command

        # Create terminal
        terminal = E2BTerminal(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            output_limit=output_byte_limit,
        )

        self._terminals[terminal_id] = terminal

        # Start the process using E2B's background execution
        try:
            # Create output handlers to collect output in real-time
            def on_stdout(data: str) -> None:
                terminal.add_output(data)

            def on_stderr(data: str) -> None:
                terminal.add_output(f"STDERR: {data}")

            # Start command in background with streaming handlers
            handle = await self.sandbox.commands.run(
                full_command,
                background=True,
                envs=env,
                cwd=cwd,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )

            terminal.set_handle(handle)
            logger.info(
                "Created E2B terminal %s (PID %s): %s",
                terminal_id,
                handle.pid,
                full_command,
            )

        except Exception as e:
            # Clean up on failure
            self._terminals.pop(terminal_id, None)
            msg = f"Failed to create E2B terminal: {e}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        else:
            return terminal_id

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
        handle = terminal._handle  # noqa: SLF001
        try:
            if handle and handle.exit_code is None:
                # Wait for the E2B command to complete
                result = await handle.wait()
                terminal.set_exit_code(result.exit_code)

                # Add any final output from the final result
                # (streaming output is already collected via callbacks)

        except Exception:
            logger.exception("Error waiting for terminal %s", terminal_id)
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_terminal(self, terminal_id: str) -> None:
        """Kill a running terminal using E2B's process management."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        try:
            # Kill the E2B process using the PID
            if terminal.pid and terminal.is_running():
                killed = await self.sandbox.commands.kill(terminal.pid)
                if killed:
                    terminal.set_exit_code(130)  # SIGINT exit code
                    logger.info(
                        "Killed E2B terminal %s (PID %s)", terminal_id, terminal.pid
                    )
                else:
                    logger.warning(
                        "Failed to kill E2B terminal %s (PID %s) - process not found",
                        terminal_id,
                        terminal.pid,
                    )
                    terminal.set_exit_code(1)

        except Exception:
            logger.exception("Error killing terminal %s", terminal_id)
            terminal.set_exit_code(1)

    async def release_terminal(self, terminal_id: str) -> None:
        """Release terminal resources."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        # Kill if still running
        if terminal.is_running():
            await self.kill_terminal(terminal_id)

        # Remove from tracking
        del self._terminals[terminal_id]
        logger.info("Released E2B terminal %s", terminal_id)

    def list_processes(self) -> dict[str, dict[str, Any]]:
        """List all tracked terminals and their status."""
        result = {}
        for terminal_id, terminal in self._terminals.items():
            result[terminal_id] = {
                "terminal_id": terminal_id,
                "command": terminal.command,
                "args": terminal.args,
                "cwd": terminal.cwd,
                "pid": terminal.pid,
                "created_at": terminal.created_at.isoformat(),
                "is_running": terminal.is_running(),
                "exit_code": terminal.get_exit_code(),
                "output_limit": terminal.output_limit,
            }
        return result

    async def get_sandbox_processes(self) -> dict[int, dict[str, Any]]:
        """Get all processes running in the E2B sandbox."""
        try:
            # Use E2B's list command to get all running processes
            processes = await self.sandbox.commands.list()
            result = {}
            for process_info in processes:
                result[process_info.pid] = {
                    "pid": process_info.pid,
                    "tag": process_info.tag,
                    "command": process_info.cmd,
                    "args": process_info.args,
                    "cwd": process_info.cwd,
                    "envs": process_info.envs,
                }
        except Exception:
            logger.exception("Error listing sandbox processes")
            return {}
        else:
            return result

    async def connect_to_process(
        self,
        pid: int,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Connect to an existing process in the sandbox and manage it as a terminal."""
        terminal_id = f"e2b_conn_{uuid.uuid4().hex[:8]}"

        try:
            # Get process info first
            processes = await self.get_sandbox_processes()
            if pid not in processes:
                msg = f"Process {pid} not found in sandbox"
                raise ValueError(msg)  # noqa: TRY301

            process_info = processes[pid]

            # Create terminal for the existing process
            terminal = E2BTerminal(
                terminal_id=terminal_id,
                command=process_info["command"],
                args=process_info.get("args", []),
                cwd=process_info.get("cwd"),
                env=process_info.get("envs", {}),
                pid=pid,
                output_limit=output_byte_limit,
            )

            def on_stdout(data: str) -> None:
                terminal.add_output(data)

            def on_stderr(data: str) -> None:
                terminal.add_output(f"STDERR: {data}")

            # Connect to the existing process
            handle = await self.sandbox.commands.connect(
                pid=pid,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )

            terminal.set_handle(handle)
            self._terminals[terminal_id] = terminal

            logger.info("Connected to E2B process %s as terminal %s", pid, terminal_id)

        except Exception as e:
            msg = f"Failed to connect to process {pid}: {e}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        else:
            return terminal_id

    async def send_stdin(self, terminal_id: str, data: str) -> None:
        """Send data to terminal stdin (if supported)."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        if not terminal.pid:
            msg = f"Terminal {terminal_id} has no process ID"
            raise ValueError(msg)

        try:
            await self.sandbox.commands.send_stdin(terminal.pid, data)
            logger.debug(
                "Sent stdin to terminal %s (PID %s): %r",
                terminal_id,
                terminal.pid,
                data[:50],
            )
        except Exception:
            logger.exception("Error sending stdin to terminal %s", terminal_id)
            raise

    async def cleanup(self) -> None:
        """Clean up all terminals."""
        logger.info("Cleaning up %s E2B terminals", len(self._terminals))
        if cleanup_tasks := [self.release_terminal(id_) for id_ in self._terminals]:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        logger.info("E2B terminal cleanup completed")
