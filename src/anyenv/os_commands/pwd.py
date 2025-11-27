"""Pwd command implementations for different operating systems."""

from __future__ import annotations

from .base import PwdCommand


class UnixPwdCommand(PwdCommand):
    """Unix/Linux pwd command implementation."""

    def create_command(self) -> str:
        """Generate Unix pwd command.

        Returns:
            The pwd command string
        """
        return "pwd"

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse Unix pwd result.

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Current working directory or None on failure
        """
        if exit_code != 0:
            return None
        path = output.strip()
        return path if path else None


class MacOSPwdCommand(PwdCommand):
    """macOS pwd command implementation."""

    def create_command(self) -> str:
        """Generate pwd command (same as Unix).

        Returns:
            The pwd command string
        """
        return "pwd"

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse pwd result (same as Unix).

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Current working directory or None on failure
        """
        if exit_code != 0:
            return None
        path = output.strip()
        return path if path else None


class WindowsPwdCommand(PwdCommand):
    """Windows pwd command implementation."""

    def create_command(self) -> str:
        """Generate Windows cd command (prints current directory when no args).

        Returns:
            The cd command string
        """
        return "cd"

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse Windows cd result.

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Current working directory or None on failure
        """
        if exit_code != 0:
            return None
        path = output.strip()
        return path if path else None


if __name__ == "__main__":
    import subprocess

    cmd = UnixPwdCommand()
    cmd_str = cmd.create_command()
    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    path = cmd.parse_command(result.stdout, result.returncode)
    print(f"Current directory: {path}")
