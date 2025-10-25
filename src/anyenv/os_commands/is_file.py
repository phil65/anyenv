"""Is file command implementations for different operating systems."""

from __future__ import annotations

from .base import IsFileCommand


class UnixIsFileCommand(IsFileCommand):
    """Unix/Linux is file command implementation."""

    def create_command(self, path: str) -> str:
        """Generate Unix test -f command.

        Args:
            path: Path to test if it's a file

        Returns:
            The test command string
        """
        return f'test -f "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Unix test -f result based on exit code.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path is a file, False otherwise
        """
        return exit_code == 0


class MacOSIsFileCommand(IsFileCommand):
    """macOS is file command implementation."""

    def create_command(self, path: str) -> str:
        """Generate test -f command (same as Unix).

        Args:
            path: Path to test if it's a file

        Returns:
            The test command string
        """
        return f'test -f "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse test -f result based on exit code (same as Unix).

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path is a file, False otherwise
        """
        return exit_code == 0


class WindowsIsFileCommand(IsFileCommand):
    """Windows is file command implementation."""

    def create_command(self, path: str) -> str:
        """Generate PowerShell file test command.

        Args:
            path: Path to test if it's a file

        Returns:
            The PowerShell command string
        """
        return (
            f'powershell -c "'
            f'$item = Get-Item \\"{path}\\" -ErrorAction SilentlyContinue; '
            f"$item -ne $null -and -not $item.PSIsContainer"
            f'"'
        )

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse PowerShell file test result.

        Args:
            output: Raw PowerShell command output
            exit_code: Command exit code (ignored)

        Returns:
            True if path is a file, False otherwise
        """
        return output.strip().lower() == "true"
