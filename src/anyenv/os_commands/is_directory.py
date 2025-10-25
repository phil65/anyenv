"""Is directory command implementations for different operating systems."""

from __future__ import annotations

from .base import IsDirectoryCommand


class UnixIsDirectoryCommand(IsDirectoryCommand):
    """Unix/Linux is directory command implementation."""

    def create_command(self, path: str) -> str:
        """Generate Unix test -d command.

        Args:
            path: Path to test if it's a directory

        Returns:
            The test command string
        """
        return f'test -d "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Unix test -d result based on exit code.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path is a directory, False otherwise
        """
        return exit_code == 0


class MacOSIsDirectoryCommand(IsDirectoryCommand):
    """macOS is directory command implementation."""

    def create_command(self, path: str) -> str:
        """Generate test -d command (same as Unix).

        Args:
            path: Path to test if it's a directory

        Returns:
            The test command string
        """
        return f'test -d "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse test -d result based on exit code (same as Unix).

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path is a directory, False otherwise
        """
        return exit_code == 0


class WindowsIsDirectoryCommand(IsDirectoryCommand):
    """Windows is directory command implementation."""

    def create_command(self, path: str) -> str:
        """Generate PowerShell directory test command.

        Args:
            path: Path to test if it's a directory

        Returns:
            The PowerShell command string
        """
        return (
            f'powershell -c "'
            f'(Get-Item \\"{path}\\" -ErrorAction SilentlyContinue).PSIsContainer'
            f'"'
        )

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse PowerShell directory test result.

        Args:
            output: Raw PowerShell command output
            exit_code: Command exit code (ignored)

        Returns:
            True if path is a directory, False otherwise
        """
        return output.strip().lower() == "true"
