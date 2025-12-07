"""Just task runner implementation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, ClassVar, Literal

from anyenv.task_runners._base import TaskInfo, TaskRunner


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class JustRunner(TaskRunner):
    """Task runner for Just (casey/just)."""

    id: ClassVar[Literal["just"]] = "just"
    website: ClassVar[str] = "https://github.com/casey/just"
    filenames: ClassVar[list[str]] = ["justfile", "Justfile", ".justfile"]
    help_cmd: ClassVar[list[str]] = ["just", "--list"]
    logo: ClassVar[str | None] = None

    # Pattern for recipe definitions: recipe_name arg1 arg2:
    _RECIPE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(@)?([a-zA-Z_][a-zA-Z0-9_-]*)\s*[^:]*:"
    )
    # Pattern for comment directly above recipe (used as description)
    _COMMENT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^#\s*(.*)$")
    # Pattern for [doc('...')] attribute
    _DOC_ATTR_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^\[doc\(['\"](.+?)['\"]\)\]$")

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse justfile and return available recipes."""
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return self._parse_justfile(content)

    def _parse_justfile(self, content: str) -> list[TaskInfo]:
        """Parse justfile content to extract recipes."""
        tasks: list[TaskInfo] = []
        lines = content.splitlines()
        pending_comment: str | None = None
        pending_doc: str | None = None

        for line in lines:
            stripped = line.rstrip()

            # Skip empty lines (reset pending comment but keep doc attribute)
            if not stripped:
                pending_comment = None
                continue

            # Check for [doc('...')] attribute
            if doc_match := self._DOC_ATTR_PATTERN.match(stripped):
                pending_doc = doc_match.group(1)
                continue

            # Check for comment (potential description for next recipe)
            if comment_match := self._COMMENT_PATTERN.match(stripped):
                pending_comment = comment_match.group(1).strip()
                continue

            # Check for recipe definition
            if recipe_match := self._RECIPE_PATTERN.match(stripped):
                recipe_name = recipe_match.group(2)

                # Skip private recipes (prefixed with _)
                if recipe_name.startswith("_"):
                    pending_comment = None
                    pending_doc = None
                    continue

                # Doc attribute takes precedence over comment
                description = pending_doc or pending_comment

                tasks.append(TaskInfo(name=recipe_name, description=description))
                pending_comment = None
                pending_doc = None
                continue

            # Any other line resets pending comment/doc
            pending_comment = None
            pending_doc = None

        return sorted(tasks, key=lambda t: t.name)

    def get_run_command(self, task_name: str, *args: str) -> list[str]:
        """Get the just command for a specific recipe."""
        return ["just", task_name, *args]
