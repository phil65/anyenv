"""Vercel-specific terminal manager using detached command execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.log import get_logger
from anyenv.process_manager import BaseTerminal


if TYPE_CHECKING:
    from vercel.sandbox import AsyncCommand, AsyncSandbox


logger = get_logger(__name__)


@dataclass
class VercelTerminal(BaseTerminal):
    """Represents a terminal session using Vercel's command management."""

    command_id: str | None = None
    _command: AsyncCommand | None = None
    _completed: bool = False

    def is_running(self) -> bool:
        """Check if terminal is still running."""
        return not self._completed and self._exit_code is None

    def set_exit_code(self, exit_code: int) -> None:
        """Set the exit code."""
        self._exit_code = exit_code
        self._completed = True

    def set_command(self, command: AsyncCommand) -> None:
        """Set the Vercel command object."""
        self._command = command
        self.command_id = command.cmd.id


class VercelTerminalManager:
    """Terminal manager that uses Vercel's detached command execution."""

    def __init__(self, sandbox: AsyncSandbox) -> None:
        """Initialize with a Vercel sandbox instance."""
        self.sandbox = sandbox
        self._terminals: dict[str, VercelTerminal] = {}

    async def create_terminal(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        output_byte_limit: int = 1048576,
    ) -> str:
        """Create a new terminal session using Vercel's detached commands."""
        terminal_id = f"vercel_term_{uuid.uuid4().hex[:8]}"
        args = args or []
        env = env or {}

        # Create terminal
        terminal = VercelTerminal(
            terminal_id=terminal_id,
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            output_limit=output_byte_limit,
        )

        self._terminals[terminal_id] = terminal

        try:
            # Start command in detached mode using Vercel's API
            cmd = await self.sandbox.run_command_detached(
                cmd=command,
                args=args,
                cwd=cwd,
                env=env,
            )

            terminal.set_command(cmd)

            # Start background task to monitor command
            asyncio.create_task(self._monitor_command(terminal))  # noqa: RUF006

            logger.info(
                "Created Vercel terminal %s (command %s): %s %s",
                terminal_id,
                cmd.cmd.id,
                command,
                " ".join(args),
            )

        except Exception as e:
            # Clean up on failure
            self._terminals.pop(terminal_id, None)
            msg = f"Failed to create Vercel terminal: {e}"
            logger.exception(msg)
            raise RuntimeError(msg) from e
        else:
            return terminal_id

    async def _monitor_command(self, terminal: VercelTerminal) -> None:
        """Monitor Vercel command and collect output."""
        try:
            cmd = terminal._command  # noqa: SLF001
            if not cmd:
                return

            # Wait for command to complete and collect output
            result = await cmd.wait()

            # Add output to terminal buffer
            if stdout := await result.stdout():
                terminal.add_output(stdout)
            if stderr := await result.stderr():
                terminal.add_output(f"STDERR: {stderr}")

            # Set exit code
            terminal.set_exit_code(result.exit_code)

        except Exception as e:
            logger.exception("Error monitoring Vercel terminal %s", terminal.terminal_id)
            terminal.add_output(f"Terminal error: {e}\n")
            terminal.set_exit_code(1)

    async def get_command_output(self, terminal_id: str) -> tuple[str, bool, int | None]:
        """Get current output from terminal."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

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
        is_running = terminal.is_running()
        exit_code = terminal.get_exit_code()

        return output, is_running, exit_code

    async def wait_for_terminal_exit(self, terminal_id: str) -> int:
        """Wait for terminal to complete."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]
        cmd = terminal._command  # noqa: SLF001
        try:
            if cmd and terminal.is_running():
                # Wait for the Vercel command to complete
                result = await cmd.wait()

                # Add final output
                if stdout := await result.stdout():
                    terminal.add_output(stdout)
                if stderr := await result.stderr():
                    terminal.add_output(f"STDERR: {stderr}")

                terminal.set_exit_code(result.exit_code)

        except Exception:
            logger.exception("Error waiting for terminal %s", terminal_id)
            terminal.set_exit_code(1)

        return terminal.get_exit_code() or 0

    async def kill_terminal(self, terminal_id: str) -> None:
        """Kill a running terminal."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        try:
            # Vercel doesn't appear to have a direct kill command
            # So we'll mark as killed and let monitoring detect it
            if terminal.is_running():
                terminal.set_exit_code(130)  # SIGINT exit code
                logger.info(
                    "Marked Vercel terminal %s as killed (command %s)",
                    terminal_id,
                    terminal.command_id,
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

        # Remove from tracking
        del self._terminals[terminal_id]
        logger.info("Released Vercel terminal %s", terminal_id)

    def list_processes(self) -> dict[str, dict[str, Any]]:
        """List all tracked terminals and their status."""
        result = {}
        for terminal_id, terminal in self._terminals.items():
            result[terminal_id] = {
                "terminal_id": terminal_id,
                "command": terminal.command,
                "args": terminal.args,
                "cwd": terminal.cwd,
                "command_id": terminal.command_id,
                "created_at": terminal.created_at.isoformat(),
                "is_running": terminal.is_running(),
                "exit_code": terminal.get_exit_code(),
                "output_limit": terminal.output_limit,
            }
        return result

    async def get_command_info(self, terminal_id: str) -> dict[str, Any]:
        """Get detailed command information from Vercel."""
        if terminal_id not in self._terminals:
            msg = f"Terminal {terminal_id} not found"
            raise ValueError(msg)

        terminal = self._terminals[terminal_id]

        if not terminal.command_id:
            return {"error": "No command ID available"}

        try:
            # Get command details from Vercel
            command = await self.sandbox.get_command(terminal.command_id)
            return {
                "command_id": command.cmd.id,
                "command": getattr(command.cmd, "command", "unknown"),
                "status": getattr(command.cmd, "status", "unknown"),
                "exit_code": getattr(command.cmd, "exit_code", None),
                "stdout": getattr(command.cmd, "stdout", ""),
                "stderr": getattr(command.cmd, "stderr", ""),
            }
        except Exception as e:
            logger.exception("Error getting command info for terminal %s", terminal_id)
            return {"error": str(e)}

    async def cleanup(self) -> None:
        """Clean up all terminals."""
        logger.info("Cleaning up %s Vercel terminals", len(self._terminals))

        # Kill all running terminals
        cleanup_tasks = []
        for terminal_id in list(self._terminals.keys()):
            cleanup_tasks.append(self.release_terminal(terminal_id))  # noqa: PERF401

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        logger.info("Vercel terminal cleanup completed")
