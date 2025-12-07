"""Cargo task runner implementation."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath
import re
from typing import TYPE_CHECKING, ClassVar

from anyenv.task_runners._base import TaskInfo, TaskRunner


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]

_ALIAS_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*(.+)$")


@dataclass
class CargoRunner(TaskRunner):
    """Task runner for Cargo (Rust) aliases and xtask.

    Supports:
    - Aliases defined in `.cargo/config.toml` or `.cargo/config`
    - xtask convention (workspace with xtask crate)
    """

    id: ClassVar = "cargo"
    website: ClassVar = "https://doc.rust-lang.org/cargo/"
    filenames: ClassVar = [".cargo/config.toml", ".cargo/config", "xtask/Cargo.toml"]
    help_cmd: ClassVar = ["cargo", "--list"]
    logo: ClassVar[str | None] = "https://www.rust-lang.org/logos/rust-logo-512x512.png"
    # Pattern for TOML alias: name = "command" or name = ["cmd", "args"]

    async def detect(self, fs: AsyncFileSystem, cwd: str) -> bool:
        """Check if this task runner is used in the given directory."""
        # Check for cargo config with aliases
        for config_name in (".cargo/config.toml", ".cargo/config"):
            filepath = posixpath.join(cwd, config_name)
            try:
                if await fs._isfile(filepath):  # noqa: SLF001
                    content = await self._read_file(fs, filepath)
                    if "[alias]" in content:
                        return True
            except Exception:  # noqa: BLE001
                pass

        xtask_cargo = posixpath.join(cwd, "xtask", "Cargo.toml")  # Check for xtask crate
        try:
            if await fs._isfile(xtask_cargo):  # noqa: SLF001
                return True
        except Exception:  # noqa: BLE001
            pass

        return False

    async def get_config_file(self, fs: AsyncFileSystem, cwd: str) -> str | None:
        """Get the cargo config file path if it exists."""
        for config_name in (".cargo/config.toml", ".cargo/config"):
            filepath = posixpath.join(cwd, config_name)
            try:
                if await fs._isfile(filepath):  # noqa: SLF001
                    return filepath
            except Exception:  # noqa: BLE001
                pass
        return None

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse cargo config and xtask to return available tasks."""
        tasks: list[TaskInfo] = []
        # Get aliases from cargo config
        tasks.extend(await self._get_aliases(fs, cwd))
        # Get xtask commands
        tasks.extend(await self._get_xtask_commands(fs, cwd))
        return sorted(tasks, key=lambda t: t.name)

    async def _get_aliases(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse aliases from .cargo/config.toml."""
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return _parse_cargo_config(content)

    async def _get_xtask_commands(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Detect xtask commands from xtask/src/main.rs."""
        xtask_main = posixpath.join(cwd, "xtask", "src", "main.rs")
        try:
            if not await fs._isfile(xtask_main):  # noqa: SLF001
                return []
        except Exception:  # noqa: BLE001
            return []

        content = await self._read_file(fs, xtask_main)
        return _parse_xtask_main(content)

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the cargo command for a specific task.

        Args:
            task_name: Name of the task (alias or xtask:command)
            *args: Additional arguments
        """
        if task_name.startswith("xtask:"):
            # xtask command
            cmd = task_name.removeprefix("xtask:")
            return ["cargo", "xtask", cmd, *args]
        return ["cargo", task_name, *args]  # Alias


def _parse_cargo_config(content: str) -> list[TaskInfo]:
    """Parse cargo config TOML to extract aliases."""
    tasks: list[TaskInfo] = []
    in_alias_section = False
    for line in content.splitlines():
        stripped = line.strip()
        # Track section headers
        if stripped.startswith("["):
            in_alias_section = stripped == "[alias]"
            continue
        if not in_alias_section:
            continue
        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue
        if match := _ALIAS_PATTERN.match(stripped):
            alias_name, alias_value = match.groups()
            # Parse the command (could be string or array)
            description = alias_value.strip().strip('"').strip("'")
            # Handle array format: ["test", "--all"]
            if description.startswith("["):
                description = description.strip("[]").replace('"', "").replace("'", "")
                description = " ".join(p.strip() for p in description.split(","))
            tasks.append(TaskInfo(name=alias_name, description=f"cargo {description}"))

    return tasks


def _parse_xtask_main(content: str) -> list[TaskInfo]:
    """Parse xtask main.rs to extract subcommands.

    Common patterns:
    - Match on string literals: "build" | "test" | "dist"
    - Clap enum variants with comments
    """
    tasks: list[TaskInfo] = []
    # Pattern for string match arms: "command" => or "command" |
    string_cmd_pattern = re.compile(r'"([a-z][a-z0-9_-]*)"(?:\s*=>|\s*\|)')
    # Pattern for enum variants (PascalCase converted to kebab-case)
    enum_variant_pattern = re.compile(r"^\s*([A-Z][a-zA-Z0-9]*),?\s*(?://\s*(.*))?$")
    found_commands: set[str] = set()
    for line in content.splitlines():
        # Find string command matches
        for match in string_cmd_pattern.finditer(line):
            cmd = match.group(1)
            if cmd not in found_commands:
                found_commands.add(cmd)
                tasks.append(TaskInfo(name=f"xtask:{cmd}"))
        # Find enum variants (likely clap subcommands)
        if enum_match := enum_variant_pattern.match(line):
            variant = enum_match.group(1)
            comment = enum_match.group(2)
            # Convert PascalCase to kebab-case
            cmd = re.sub(r"(?<!^)(?=[A-Z])", "-", variant).lower()
            # Skip common non-command variants
            if cmd in ("self", "none", "some", "ok", "err"):
                continue
            if cmd not in found_commands:
                found_commands.add(cmd)
                tasks.append(TaskInfo(name=f"xtask:{cmd}", description=comment))

    return tasks
