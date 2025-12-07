"""Makefile task runner implementation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, ClassVar, Literal

from anyenv.task_runners._base import TaskInfo, TaskRunner


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class MakefileRunner(TaskRunner):
    """Task runner for GNU Make."""

    id: ClassVar[Literal["makefile"]] = "makefile"
    website: ClassVar[str] = "https://www.gnu.org/software/make/manual/make.html"
    filenames: ClassVar[list[str]] = ["Makefile", "makefile", "GNUmakefile"]
    help_cmd: ClassVar[list[str]] = ["make", "help"]
    logo: ClassVar[str | None] = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/39/"
        "Official_gnu.svg/2048px-Official_gnu.svg.png"
    )

    # Pattern for targets with ## comments (common convention)
    _HELP_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:.*?##\s*(.*)$"
    )
    # Pattern for simple targets (without help text)
    _TARGET_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:")
    # Pattern for .PHONY declarations
    _PHONY_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^\.PHONY\s*:\s*(.+)$")

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse Makefile and return available targets.

        Extracts targets with optional descriptions from ## comments.
        Prioritizes .PHONY targets as they represent runnable tasks.
        """
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return self._parse_makefile(content)

    def _parse_makefile(self, content: str) -> list[TaskInfo]:
        """Parse Makefile content to extract targets."""
        tasks: dict[str, TaskInfo] = {}
        phony_targets: set[str] = set()

        for line in content.splitlines():
            line = line.rstrip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Collect .PHONY targets
            if phony_match := self._PHONY_PATTERN.match(line):
                targets = phony_match.group(1).split()
                phony_targets.update(targets)
                continue

            # Try to match target with ## help comment first
            if help_match := self._HELP_PATTERN.match(line):
                target, description = help_match.groups()
                if not target.startswith("."):
                    tasks[target] = TaskInfo(name=target, description=description.strip())
                continue

            # Match simple targets
            if target_match := self._TARGET_PATTERN.match(line):
                target = target_match.group(1)
                # Skip internal targets (starting with .) and already found ones
                if not target.startswith(".") and target not in tasks:
                    tasks[target] = TaskInfo(name=target)

        # Sort: .PHONY targets first, then alphabetically
        def sort_key(item: tuple[str, TaskInfo]) -> tuple[int, str]:
            name = item[0]
            return (0 if name in phony_targets else 1, name)

        return [task for _, task in sorted(tasks.items(), key=sort_key)]

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the make command for a specific target."""
        return ["make", task_name, *args]
