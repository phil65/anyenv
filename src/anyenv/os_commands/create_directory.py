"""Create directory command implementations for different operating systems."""

from __future__ import annotations

from .base import CreateDirectoryCommand


class UnixCreateDirectoryCommand(CreateDirectoryCommand):
    """Unix/Linux create directory command implementation."""

    def create_command(self, path: str, parents: bool = True) -> str:
        """Generate Unix mkdir command.

        Args:
            path: Directory path to create
            parents: Whether to create parent directories

        Returns:
            The mkdir command string
        """
        return f'mkdir -p "{path}"' if parents else f'mkdir "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Unix mkdir result based on exit code.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if directory was created successfully, False otherwise
        """
        return exit_code == 0


class MacOSCreateDirectoryCommand(CreateDirectoryCommand):
    """macOS create directory command implementation."""

    def create_command(self, path: str, parents: bool = True) -> str:
        """Generate mkdir command (same as Unix).

        Args:
            path: Directory path to create
            parents: Whether to create parent directories

        Returns:
            The mkdir command string
        """
        return f'mkdir -p "{path}"' if parents else f'mkdir "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse mkdir result based on exit code (same as Unix).

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if directory was created successfully, False otherwise
        """
        return exit_code == 0


class WindowsCreateDirectoryCommand(CreateDirectoryCommand):
    """Windows create directory command implementation."""

    def create_command(self, path: str, parents: bool = True) -> str:
        """Generate Windows directory creation command.

        Args:
            path: Directory path to create
            parents: Whether to create parent directories

        Returns:
            The directory creation command string
        """
        if parents:
            return (
                f'powershell -c "New-Item -ItemType Directory -Path \\"{path}\\" -Force"'
            )
        return f'mkdir "{path}"'

    def parse_command(
        self,
        output: str,
        exit_code: int = 0,
    ) -> bool:
        """Parse Windows directory creation result.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if directory was created successfully, False otherwise
        """
        return exit_code == 0
