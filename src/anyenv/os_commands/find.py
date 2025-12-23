"""Find command implementations for different operating systems."""

from __future__ import annotations

from typing import Literal

from .base import FindCommand
from .models import DirectoryEntry


class UnixFindCommand(FindCommand):
    """Unix/Linux find command implementation using GNU find -printf."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
    ) -> str:
        """Generate Unix find command with -printf for size and type info.

        Uses GNU find -printf to get size, type, and path in one call.
        Output format: "<size> <type> <path>" per line
        where type is f (file), d (directory), or l (link).

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

        # Use -printf to get size, type, and path
        # %s = size in bytes, %y = type (f/d/l), %p = path
        parts.append(r"-printf '%s %y %p\n'")

        return " ".join(parts)

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse Unix find -printf output.

        Expected format: "<size> <type> <path>" per line
        where type is f (file), d (directory), or l (link).

        Args:
            output: Raw find command output
            base_path: Base path used in the find command (unused)

        Returns:
            List of DirectoryEntry objects
        """
        lines = output.strip().split("\n")
        if not lines or (len(lines) == 1 and not lines[0]):
            return []

        type_map: dict[str, Literal["file", "directory", "link"]] = {
            "f": "file",
            "d": "directory",
            "l": "link",
        }
        expected_parts = 3  # size, type, path

        entries: list[DirectoryEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse: "<size> <type> <path>"
            parts = line.split(" ", 2)
            if len(parts) < expected_parts:
                continue

            # Parse size
            try:
                size = int(parts[0])
            except ValueError:
                size = 0

            # Get type
            entry_type = type_map.get(parts[1], "file")
            file_path = parts[2]

            # Extract name from path
            name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

            # Skip . and ..
            if name in (".", ".."):
                continue

            entries.append(
                DirectoryEntry(
                    name=name,
                    path=file_path,
                    type=entry_type,
                    size=size,
                    timestamp=None,
                    permissions=None,
                )
            )

        return entries


class MacOSFindCommand(FindCommand):
    """macOS find command implementation (BSD find with stat for size/type)."""

    def create_command(
        self,
        path: str,
        pattern: str | None = None,
        maxdepth: int | None = None,
        file_type: Literal["file", "directory", "all"] = "all",
    ) -> str:
        """Generate macOS find command with stat for size and type info.

        BSD find doesn't support -printf, so we use -exec stat to get info.
        Output format: "<size> <type> <path>" per line
        where type is Regular (file), Directory, or Link.

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

        # Use -exec stat to get size and type
        # %z = size in bytes, %HT = file type, %N = path
        parts.append(r"-exec stat -f '%z %HT %N' {} \;")

        return " ".join(parts)

    def parse_command(self, output: str, base_path: str = "") -> list[DirectoryEntry]:
        """Parse macOS find + stat output.

        Expected format: "<size> <type> <path>" per line
        where type is "Regular File", "Directory", "Symbolic Link", etc.

        Args:
            output: Raw find command output
            base_path: Base path used in the find command (unused)

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

            # Parse: "<size> <type> <path>"
            # Type can be multi-word like "Regular File" or "Symbolic Link"
            parts = line.split(" ", 1)
            min_parts = 2
            if len(parts) < min_parts:
                continue

            # Parse size
            try:
                size = int(parts[0])
            except ValueError:
                size = 0

            remainder = parts[1]

            # Determine type and extract path
            entry_type: Literal["file", "directory", "link"]
            if remainder.startswith("Directory "):
                entry_type = "directory"
                file_path = remainder[10:]  # len("Directory ")
            elif remainder.startswith("Symbolic Link "):
                entry_type = "link"
                file_path = remainder[14:]  # len("Symbolic Link ")
            elif remainder.startswith("Regular File "):
                entry_type = "file"
                file_path = remainder[13:]  # len("Regular File ")
            else:
                # Unknown type, try to find path after type word
                type_parts = remainder.split(" ", 1)
                entry_type = "file"
                file_path = type_parts[1] if len(type_parts) > 1 else remainder

            # Extract name from path
            name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

            # Skip . and ..
            if name in (".", ".."):
                continue

            entries.append(
                DirectoryEntry(
                    name=name,
                    path=file_path,
                    type=entry_type,
                    size=size,
                    timestamp=None,
                    permissions=None,
                )
            )

        return entries


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
