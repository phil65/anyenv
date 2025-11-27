"""Which command implementations for different operating systems."""

from __future__ import annotations

from .base import WhichCommand


class UnixWhichCommand(WhichCommand):
    """Unix/Linux which command implementation."""

    def create_command(self, executable: str) -> str:
        """Generate Unix which command.

        Args:
            executable: Name of executable to find

        Returns:
            The which command string
        """
        return f'which "{executable}"'

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse Unix which result.

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Path to executable or None if not found
        """
        if exit_code != 0:
            return None
        path = output.strip()
        return path if path else None


class MacOSWhichCommand(WhichCommand):
    """macOS which command implementation."""

    def create_command(self, executable: str) -> str:
        """Generate which command (same as Unix).

        Args:
            executable: Name of executable to find

        Returns:
            The which command string
        """
        return f'which "{executable}"'

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse which result (same as Unix).

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Path to executable or None if not found
        """
        if exit_code != 0:
            return None
        path = output.strip()
        return path if path else None


class WindowsWhichCommand(WhichCommand):
    """Windows where command implementation."""

    def create_command(self, executable: str) -> str:
        """Generate Windows where command.

        Args:
            executable: Name of executable to find

        Returns:
            The where command string
        """
        return f'where "{executable}"'

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse Windows where result.

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Path to first matching executable or None if not found
        """
        if exit_code != 0:
            return None
        # where can return multiple paths, take the first one
        lines = output.strip().splitlines()
        return lines[0].strip() if lines else None


if __name__ == "__main__":
    import subprocess

    cmd = UnixWhichCommand()
    cmd_str = cmd.create_command("python")
    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    path = cmd.parse_command(result.stdout, result.returncode)
    print(f"Python path: {path}")
