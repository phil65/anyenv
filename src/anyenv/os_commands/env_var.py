"""Environment variable command implementations for different operating systems."""

from __future__ import annotations

from ._quoting import powershell, ps_literal, sh_quote
from .base import EnvVarCommand


class UnixEnvVarCommand(EnvVarCommand):
    """Unix/Linux environment variable command implementation."""

    def create_command(self, name: str) -> str:
        """Generate Unix printenv command.

        Args:
            name: Name of environment variable

        Returns:
            The printenv command string
        """
        return f"printenv {sh_quote(name)}"

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse Unix printenv result.

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Variable value or None if not set
        """
        if exit_code != 0:
            return None
        # printenv includes trailing newline
        return output.rstrip("\n") if output else None


class MacOSEnvVarCommand(EnvVarCommand):
    """macOS environment variable command implementation."""

    def create_command(self, name: str) -> str:
        """Generate printenv command (same as Unix).

        Args:
            name: Name of environment variable

        Returns:
            The printenv command string
        """
        return f"printenv {sh_quote(name)}"

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse printenv result (same as Unix).

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Variable value or None if not set
        """
        if exit_code != 0:
            return None
        return output.rstrip("\n") if output else None


class WindowsEnvVarCommand(EnvVarCommand):
    """Windows environment variable command implementation."""

    def create_command(self, name: str) -> str:
        """Generate PowerShell environment variable command.

        Args:
            name: Name of environment variable

        Returns:
            The PowerShell command string
        """
        return powershell(f"[Environment]::GetEnvironmentVariable({ps_literal(name)})")

    def parse_command(self, output: str, exit_code: int = 0) -> str | None:
        """Parse PowerShell environment variable result.

        Args:
            output: Raw command output
            exit_code: Command exit code

        Returns:
            Variable value or None if not set
        """
        # PowerShell returns empty string for unset variables
        value = output.strip()
        return value if value else None


if __name__ == "__main__":
    import subprocess

    cmd = UnixEnvVarCommand()
    cmd_str = cmd.create_command("HOME")
    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    value = cmd.parse_command(result.stdout, result.returncode)
    print(f"HOME: {value}")
