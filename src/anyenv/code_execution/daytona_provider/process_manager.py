"""Daytona-specific terminal manager using session-based process management."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager import BaseTerminal, TerminalManagerProtocol


if TYPE_CHECKING:
    from daytona._async.sandbox import AsyncSandbox


logger = get_logger(__name__)


@dataclass
class DaytonaTerminal(BaseTerminal):
    """Represents a terminal session using Daytona's session management."""

    session_id: str
    command_id: str | None = None
    _completed: bool = False

    def is_running(self) -> bool:
        """Check if terminal is still running."""
        return not self._completed and self._exit_code is None

    def set_exit_code(self, exit_code: int) -> None:
        """Set the exit code."""
        self._exit_code = exit_code
        self._completed = True

    def set_command_id(self, command_id: str) -> None:
        """Set the Daytona command ID."""
        self.command_id = command_id


class DaytonaTerminalManager(TerminalManagerProtocol):
    """Terminal manager that uses Daytona's session-based process management."""

    def __init__(self, sandbox: AsyncSandbox) -> None:
        """Initialize with a Daytona sandbox instance."""
        self.sandbox = sandbox
        self._terminals: dict[str, DaytonaTerminal] = {}

    async def create_terminal(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Create a new terminal session using Daytona's session management."""
        terminal_id = f"daytona_term_{uuid.uuid4().hex[:8]}"
        args = args or []
        env = env or {}

        # Build full command
        full_command = f"{command} {' '.join(args)}" if args else command

        # Create unique session ID for this terminal
        session_id = f"term_session_{uuid.uuid4().hex[:8]}"

        # Create terminal
        terminal = DaytonaTerminal(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            session_id=session_id,
            output_limit=output_byte_limit,
        )

        self._terminals[terminal_id] = terminal

        try:
            # Create Daytona session
            await self.sandbox.process.create_session(session_id)

            # Start the command asynchronously in the session
            from daytona.common.process import SessionExecuteRequest

            request = SessionExecuteRequest(command=full_command, runAsync=True)
            response = await self.sandbox.process.execute_session_command(
                session_id, request
            )

            # Store the command ID for tracking
            terminal.set_command_id(str(response.cmd_id))

            # Start background task to collect output
            asyncio.create_task(self._collect_output(terminal))  # noqa: RUF006

            logger.info(
                "Created Daytona terminal %s (session %s, command %s): %s",
                terminal_id,
                session_id,
                response.cmd_id,
                full_command,
            )

        except Exception as e:
            # Clean up on failure
            self._terminals.pop(terminal_id, None)
            with contextlib.suppress(Exception):
                await self.sandbox.process.delete_session(session_id)
            msg = f"Failed to create Daytona terminal: {e}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        else:
            return terminal_id

    async def _collect_output(self, terminal: DaytonaTerminal) -> None:
        """Collect output from Daytona session command using streaming logs."""
        try:
            if not terminal.command_id:
                return

            # Use Daytona's streaming logs to collect output in real-time
            def on_logs(chunk: str) -> None:
                terminal.add_output(chunk)

            await self.sandbox.process.get_session_command_logs_async(
                terminal.session_id, terminal.command_id, on_logs
            )

            # Get final command info for exit code
            command_info = await self.sandbox.process.get_session_command(
                terminal.session_id, terminal.command_id
            )
            if command_info.exit_code is not None:
                terminal.set_exit_code(int(command_info.exit_code))

        except Exception as e:
            logger.exception(
                "Error collecting output for Daytona terminal %s", terminal.terminal_id
            )
            terminal.add_output(f"Terminal error: {e}\n")
            terminal.set_exit_code(1)

    async def get_command_output(self, terminal_id: str) -> tuple[str, bool, int | None]:
        """Get current output from terminal."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        # Try to update exit code if command is done
        if terminal.command_id and terminal.is_running():
            try:
                command_info = await self.sandbox.process.get_session_command(
                    terminal.session_id, terminal.command_id
                )
                if command_info.exit_code is not None:
                    terminal.set_exit_code(int(command_info.exit_code))
            except Exception:  # noqa: BLE001
                pass  # Best effort

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
            # Poll for command completion
            while terminal.is_running():
                await asyncio.sleep(0.5)
                if terminal.command_id:
                    try:
                        command_info = await self.sandbox.process.get_session_command(
                            terminal.session_id, terminal.command_id
                        )
                        if command_info.exit_code is not None:
                            terminal.set_exit_code(int(command_info.exit_code))
                            break
                    except Exception:  # noqa: BLE001
                        continue

        except Exception:
            logger.exception("Error waiting for terminal %s", terminal_id)
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_terminal(self, terminal_id: str) -> None:
        """Kill a running terminal by deleting its session."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        try:
            # Delete the Daytona session to kill all its commands
            if terminal.is_running():
                await self.sandbox.process.delete_session(terminal.session_id)
                terminal.set_exit_code(130)  # SIGINT exit code
                logger.info(
                    "Killed Daytona terminal %s (session %s)",
                    terminal_id,
                    terminal.session_id,
                )

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

        # Clean up session
        with contextlib.suppress(Exception):
            await self.sandbox.process.delete_session(terminal.session_id)

        # Remove from tracking
        del self._terminals[terminal_id]
        logger.info("Released Daytona terminal %s", terminal_id)

    def list_processes(self) -> dict[str, dict[str, Any]]:
        """List all tracked terminals and their status."""
        result = {}
        for terminal_id, terminal in self._terminals.items():
            result[terminal_id] = {
                "terminal_id": terminal_id,
                "command": terminal.command,
                "args": terminal.args,
                "cwd": terminal.cwd,
                "session_id": terminal.session_id,
                "command_id": terminal.command_id,
                "created_at": terminal.created_at.isoformat(),
                "is_running": terminal.is_running(),
                "exit_code": terminal.get_exit_code(),
                "output_limit": terminal.output_limit,
            }
        return result

    async def get_sandbox_sessions(self) -> dict[str, dict[str, Any]]:
        """Get all sessions in the Daytona sandbox."""
        try:
            # Use Daytona's list_sessions to get all active sessions
            sessions = await self.sandbox.process.list_sessions()
            result = {}
            for session in sessions:
                result[session.session_id] = {
                    "session_id": session.session_id,
                    "commands": [
                        {
                            "id": cmd.id,
                            "command": cmd.command,
                            "exit_code": cmd.exit_code,
                        }
                        for cmd in session.commands or []
                    ],
                }
        except Exception:
            logger.exception("Error listing sandbox sessions")
            return {}
        else:
            return result

    async def connect_to_session(
        self,
        session_id: str,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Connect to an existing session in the sandbox and manage it as a terminal."""
        terminal_id = f"daytona_conn_{uuid.uuid4().hex[:8]}"

        try:
            # Get session info
            session = await self.sandbox.process.get_session(session_id)

            # Create terminal for the existing session
            # Use the last command if available
            last_command = session.commands[-1] if session.commands else None
            command_text = last_command.command if last_command else "unknown"

            terminal = DaytonaTerminal(
                terminal_id=terminal_id,
                command=command_text,
                args=[],
                cwd=None,
                env={},
                session_id=session_id,
                output_limit=output_byte_limit,
            )

            if last_command:
                terminal.set_command_id(last_command.id)
                if last_command.exit_code is not None:
                    terminal.set_exit_code(int(last_command.exit_code))

            self._terminals[terminal_id] = terminal

            # Start collecting output if command is still running
            if terminal.is_running():
                asyncio.create_task(self._collect_output(terminal))  # noqa: RUF006

            logger.info(
                "Connected to Daytona session %s as terminal %s", session_id, terminal_id
            )

        except Exception as e:
            msg = f"Failed to connect to session {session_id}: {e}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        else:
            return terminal_id

    async def execute_in_session(
        self, terminal_id: str, command: str, run_async: bool = True
    ) -> str:
        """Execute a new command in an existing terminal session."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        try:
            from daytona.common.process import SessionExecuteRequest

            request = SessionExecuteRequest(command=command, runAsync=run_async)
            response = await self.sandbox.process.execute_session_command(
                terminal.session_id, request
            )

            # Update terminal with new command info
            terminal.set_command_id(str(response.cmd_id))
            terminal._completed = False  # noqa: SLF001
            terminal._exit_code = None  # noqa: SLF001

            # Start collecting output for the new command
            if run_async:
                asyncio.create_task(self._collect_output(terminal))  # noqa: RUF006

            logger.info(
                "Executed command in terminal %s (session %s): %s",
                terminal_id,
                terminal.session_id,
                command,
            )
            return str(response.cmd_id)

        except Exception:
            logger.exception("Error executing command in terminal %s", terminal_id)
            raise

    async def cleanup(self) -> None:
        """Clean up all terminals and their sessions."""
        logger.info("Cleaning up %s Daytona terminals", len(self._terminals))
        if cleanup_tasks := [self.release_terminal(id_) for id_ in self._terminals]:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        logger.info("Daytona terminal cleanup completed")
