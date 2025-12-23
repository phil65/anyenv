"""Find command implementations for different operating systems."""

from __future__ import annotations

from typing import Literal

from .base import FindCommand
from .models import DirectoryEntry


class UnixFindCommand(FindCommand):
    """Unix/Linux find command implementation."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
    ) -> str:
        """Generate Unix find command.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend
            file_type: Filter by type - files only, directories only, or all

        Returns:
            The find command string
        """
        parts = ["find", f'"{path}"']

        if maxdepth is not None:
            parts.append(f"-maxdepth {maxdepth}")

        if file_type == "file":
            parts.append("-type f")
        elif file_type == "directory":
            parts.append("-type d")
        # "all" doesn't add a type filter

        if pattern:
            parts.append(f'-name "{pattern}"')

        return " ".join(parts)

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse Unix find output.

        Args:
            output: Raw find command output (one path per line)
            base_path: Base path used in the find command

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines or (len(lines) == 1 and not lines[0]):
            return []

        entries: list[DirectoryEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Extract name from path
            name = line.rsplit("/", 1)[-1] if "/" in line else line

            # Skip . and ..
            if name in (".", ".."):
                continue

            # We can't determine type from find output alone without -ls
            # Default to file, caller can use -type to filter
            entries.append(
                DirectoryEntry(
                    name=name,
                    path=line,
                    type="file",  # Default; use file_type param to filter
                    size=0,  # Not available from basic find output
                    timestamp=None,
                    permissions=None,
                )
            )

        return entries


class MacOSFindCommand(FindCommand):
    """macOS find command implementation (BSD find)."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
    ) -> str:
        """Generate macOS find command.

        BSD find uses the same syntax as GNU find for basic operations.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend
            file_type: Filter by type - files only, directories only, or all

        Returns:
            The find command string
        """
        # BSD find has same syntax for these basic operations
        parts = ["find", f'"{path}"']

        if maxdepth is not None:
            parts.append(f"-maxdepth {maxdepth}")

        if file_type == "file":
            parts.append("-type f")
        elif file_type == "directory":
            parts.append("-type d")

        if pattern:
            parts.append(f'-name "{pattern}"')

        return " ".join(parts)

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse macOS find output.

        Args:
            output: Raw find command output (one path per line)
            base_path: Base path used in the find command

        Returns:
            List of DirectoryEntry objects
        """
        # Same parsing as Unix
        unix_cmd = UnixFindCommand()
        return unix_cmd.parse_command(output, base_path)


class WindowsFindCommand(FindCommand):
    """Windows find command implementation using PowerShell."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
    ) -> str:
        """Generate Windows PowerShell Get-ChildItem command.

        Args:
            path: Directory to search in
            pattern: Glob pattern for name matching (e.g., "*.py")
            maxdepth: Maximum directory depth to descend
            file_type: Filter by type - files only, directories only, or all

        Returns:
            The PowerShell command string
        """
        # Build Get-ChildItem command
        parts = [f'Get-ChildItem -Path \\"{path}\\" -Recurse']

        if maxdepth is not None:
            # PowerShell -Depth is 0-indexed (0 = immediate children only)
            # To match find behavior where maxdepth 1 = immediate children
            depth = maxdepth - 1 if maxdepth > 0 else 0
            parts.append(f"-Depth {depth}")

        if pattern:
            parts.append(f'-Filter \\"{pattern}\\"')

        if file_type == "file":
            parts.append("-File")
        elif file_type == "directory":
            parts.append("-Directory")

        # Output format: FullName|Length|Mode (pipe-separated for easy parsing)
        parts.append('| ForEach-Object { \\"$($_.FullName)|$($_.Length)|$($_.Mode)\\" }')

        return f'powershell -c "{" ".join(parts)}"'

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse Windows PowerShell Get-ChildItem output.

        Args:
            output: Raw command output (path|size|mode per line)
            base_path: Base path used in the command

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines or (len(lines) == 1 and not lines[0]):
            return []

        entries: list[DirectoryEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 3:  # noqa: PLR2004
                continue

            full_path = parts[0]
            size_str = parts[1]
            mode = parts[2]

            # Extract name from path
            name = full_path.rsplit("\\", 1)[-1] if "\\" in full_path else full_path

            # Skip . and ..
            if name in (".", ".."):
                continue

            # Determine type from mode
            file_type: Literal["file", "directory", "link"]
            file_type = "directory" if mode.startswith("d") else "file"

            # Parse size
            try:
                size = int(size_str) if size_str else 0
            except ValueError:
                size = 0

            entries.append(
                DirectoryEntry(
                    name=name,
                    path=full_path,
                    type=file_type,
                    size=size,
                    timestamp=None,
                    permissions=mode,
                )
            )

        return entries


if __name__ == "__main__":
    import subprocess
    import sys

    # Test on current platform
    if sys.platform == "win32":
        cmd = WindowsFindCommand()
    elif sys.platform == "darwin":
        cmd = MacOSFindCommand()
    else:
        cmd = UnixFindCommand()

    cmd_str = cmd.create_command(".", pattern="*.py", maxdepth=2, file_type="file")
    print(f"Command: {cmd_str}")

    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    entries = cmd.parse_command(result.stdout, ".")

    print(f"\nFound {len(entries)} entries:")
    for entry in entries[:5]:  # Show first 5 entries
        print(f"  {entry.path} ({entry.type})")
