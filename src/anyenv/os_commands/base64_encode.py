"""Base64 encode command implementations for different operating systems."""

from __future__ import annotations

import base64

from anyenv.os_commands.base import Base64EncodeCommand


class UnixBase64EncodeCommand(Base64EncodeCommand):
    """Unix/Linux base64 encode command implementation."""

    def create_command(self, path: str) -> str:
        """Generate Unix base64 command.

        Args:
            path: Path to file to encode

        Returns:
            The base64 command string
        """
        return f'base64 "{path}"'

    def parse_command(self, output: str) -> bytes:
        """Parse Unix base64 output.

        Args:
            output: Raw base64 encoded output

        Returns:
            Decoded bytes
        """
        # Remove any whitespace/newlines that base64 command may add
        cleaned = output.replace("\n", "").replace("\r", "").strip()
        return base64.b64decode(cleaned)


class MacOSBase64EncodeCommand(Base64EncodeCommand):
    """macOS base64 encode command implementation."""

    def create_command(self, path: str) -> str:
        """Generate macOS base64 command.

        Args:
            path: Path to file to encode

        Returns:
            The base64 command string
        """
        # macOS base64 uses -i for input file
        return f'base64 -i "{path}"'

    def parse_command(self, output: str) -> bytes:
        """Parse macOS base64 output.

        Args:
            output: Raw base64 encoded output

        Returns:
            Decoded bytes
        """
        cleaned = output.replace("\n", "").replace("\r", "").strip()
        return base64.b64decode(cleaned)


class WindowsBase64EncodeCommand(Base64EncodeCommand):
    """Windows base64 encode command implementation using PowerShell."""

    def create_command(self, path: str) -> str:
        """Generate PowerShell base64 encode command.

        Args:
            path: Path to file to encode

        Returns:
            The PowerShell command string
        """
        # Use PowerShell to read file and convert to base64
        return f'powershell -c "[Convert]::ToBase64String([IO.File]::ReadAllBytes(\\"{path}\\"))"'

    def parse_command(self, output: str) -> bytes:
        """Parse PowerShell base64 output.

        Args:
            output: Raw base64 encoded output

        Returns:
            Decoded bytes
        """
        cleaned = output.replace("\n", "").replace("\r", "").strip()
        return base64.b64decode(cleaned)


if __name__ == "__main__":
    from pathlib import Path
    import subprocess
    import tempfile

    # Create a test file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        test_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        f.write(test_data)
        test_path = f.name

    try:
        cmd = UnixBase64EncodeCommand()
        cmd_str = cmd.create_command(test_path)
        result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        decoded = cmd.parse_command(result.stdout)
        print(f"Original: {test_data!r}")
        print(f"Decoded:  {decoded!r}")
        print(f"Match: {test_data == decoded}")
    finally:
        Path(test_path).unlink()
