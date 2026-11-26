"""Copy path command implementations for different operating systems."""

from ._quoting import powershell, ps_literal, sh_path
from .base import CopyPathCommand


class UnixCopyPathCommand(CopyPathCommand):
    """Unix/Linux copy path command implementation."""

    def create_command(self, source: str, destination: str, recursive: bool = False) -> str:
        """Generate Unix cp command.

        Args:
            source: Source path to copy from
            destination: Destination path to copy to
            recursive: Whether to copy directories recursively

        Returns:
            The cp command string
        """
        if recursive:
            return f"cp -r {sh_path(source)} {sh_path(destination)}"
        return f"cp {sh_path(source)} {sh_path(destination)}"

    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse Unix cp result based on exit code.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if copy was successful, False otherwise
        """
        return exit_code == 0


class MacOSCopyPathCommand(CopyPathCommand):
    """macOS copy path command implementation."""

    def create_command(self, source: str, destination: str, recursive: bool = False) -> str:
        """Generate cp command (same as Unix).

        Args:
            source: Source path to copy from
            destination: Destination path to copy to
            recursive: Whether to copy directories recursively

        Returns:
            The cp command string
        """
        if recursive:
            return f"cp -r {sh_path(source)} {sh_path(destination)}"
        return f"cp {sh_path(source)} {sh_path(destination)}"

    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse cp result based on exit code (same as Unix).

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if copy was successful, False otherwise
        """
        return exit_code == 0


class WindowsCopyPathCommand(CopyPathCommand):
    """Windows copy path command implementation."""

    def create_command(self, source: str, destination: str, recursive: bool = False) -> str:
        """Generate Windows copy command.

        Args:
            source: Source path to copy from
            destination: Destination path to copy to
            recursive: Whether to copy directories recursively

        Returns:
            The copy command string
        """
        script = f"Copy-Item -LiteralPath {ps_literal(source)} {ps_literal(destination)} -Force"
        return powershell(f"{script} -Recurse" if recursive else script)

    def parse_command(self, output: str, exit_code: int = 0) -> bool:
        """Parse Windows copy result.

        Args:
            output: Raw command output (ignored)
            exit_code: Command exit code

        Returns:
            True if copy was successful, False otherwise
        """
        return exit_code == 0
