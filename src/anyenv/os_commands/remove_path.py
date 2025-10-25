"""Remove path command implementations for different operating systems."""

from __future__ import annotations

from .base import RemovePathCommand


class UnixRemovePathCommand(RemovePathCommand):
    """Unix/Linux remove path command implementation."""

    def create_command(self, path: str, recursive: bool = False) -> str:
        """Generate Unix rm command.

        Args:
            path: Path to remove
            recursive: Whether to remove directories recursively

        Returns:
            The rm command string
        """
        return f'rm -rf "{path}"' if recursive else f'rm "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Unix rm result based on exit code.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path was removed successfully, False otherwise
        """
        return exit_code == 0


class MacOSRemovePathCommand(RemovePathCommand):
    """macOS remove path command implementation."""

    def create_command(self, path: str, recursive: bool = False) -> str:
        """Generate rm command (same as Unix).

        Args:
            path: Path to remove
            recursive: Whether to remove directories recursively

        Returns:
            The rm command string
        """
        return f'rm -rf "{path}"' if recursive else f'rm "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse rm result based on exit code (same as Unix).

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path was removed successfully, False otherwise
        """
        return exit_code == 0


class WindowsRemovePathCommand(RemovePathCommand):
    """Windows remove path command implementation."""

    def create_command(self, path: str, recursive: bool = False) -> str:
        """Generate Windows removal command.

        Args:
            path: Path to remove
            recursive: Whether to remove directories recursively

        Returns:
            The removal command string
        """
        if recursive:
            return f'powershell -c "Remove-Item \\"{path}\\" -Recurse -Force"'
        return f'del "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Windows removal result.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if path was removed successfully, False otherwise
        """
        return exit_code == 0
