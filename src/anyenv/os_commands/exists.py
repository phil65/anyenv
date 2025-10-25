"""Exists command implementations for different operating systems."""

from __future__ import annotations

from .base import ExistsCommand


class UnixExistsCommand(ExistsCommand):
    """Unix/Linux exists command implementation."""

    def create_command(self, path: str) -> str:
        """Generate Unix test -e command.

        Args:
            path: Path to test for existence

        Returns:
            The test command string
        """
        return f'test -e "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Unix test result based on exit code.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path exists, False otherwise
        """
        return exit_code == 0


class MacOSExistsCommand(ExistsCommand):
    """macOS exists command implementation."""

    def create_command(self, path: str) -> str:
        """Generate test -e command (same as Unix).

        Args:
            path: Path to test for existence

        Returns:
            The test command string
        """
        return f'test -e "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse test result based on exit code (same as Unix).

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path exists, False otherwise
        """
        return exit_code == 0


class WindowsExistsCommand(ExistsCommand):
    """Windows exists command implementation."""

    def create_command(self, path: str) -> str:
        """Generate PowerShell Test-Path command.

        Args:
            path: Path to test for existence

        Returns:
            The PowerShell command string
        """
        return f'powershell -c "Test-Path \\"{path}\\""'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse PowerShell Test-Path result.

        Args:
            output: Raw PowerShell command output
            exit_code: Command exit code (ignored)

        Returns:
            True if path exists, False otherwise
        """
        return output.strip().lower() == "true"
