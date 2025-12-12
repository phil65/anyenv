"""NPM/package.json task runner implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import posixpath
import re
import shutil
from typing import TYPE_CHECKING, ClassVar, Literal

from anyenv.task_runners._base import TaskInfo, TaskRunner


if TYPE_CHECKING:
    from exxec import ExecutionEnvironment
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


type PackageManagerStr = Literal["npm", "pnpm", "yarn", "bun"]

LOCKFILE_TO_MANAGER: dict[str, PackageManagerStr] = {
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "bun.lock": "bun",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
}

MANAGER_RUN_CMD: dict[PackageManagerStr, list[str]] = {
    "npm": ["npm", "run"],
    "pnpm": ["pnpm", "run"],
    "yarn": ["yarn", "run"],
    "bun": ["bun", "run"],
}


@dataclass
class PackageJsonRunner(TaskRunner):
    """Task runner for package.json scripts."""

    id: ClassVar[Literal["npm"]] = "npm"
    website: ClassVar[str] = "https://docs.npmjs.com/cli/v10/using-npm/scripts"
    filenames: ClassVar[list[str]] = ["package.json"]
    help_cmd: ClassVar[list[str]] = ["npm", "run"]
    logo: ClassVar[str | None] = (
        "https://raw.githubusercontent.com/npm/logos/master/npm%20square/n-64.png"
    )

    _detected_manager: PackageManagerStr | None = field(default=None, repr=False)

    async def detect_package_manager(self, fs: AsyncFileSystem, cwd: str) -> PackageManagerStr:
        """Detect which package manager to use.

        Detection order:
        1. Lock file presence
        2. packageManager field in package.json
        3. First available on system
        4. Default to npm
        """
        # Check lock files
        for lockfile, manager in LOCKFILE_TO_MANAGER.items():
            filepath = posixpath.join(cwd, lockfile)
            try:
                if await fs._isfile(filepath):  # noqa: SLF001
                    return manager
            except Exception:  # noqa: BLE001
                pass

        # Check packageManager field in package.json
        package_json = posixpath.join(cwd, "package.json")
        try:
            if await fs._isfile(package_json):  # noqa: SLF001
                content = await self._read_file(fs, package_json)
                data = json.loads(content)
                if (pm_field := data.get("packageManager")) and (
                    match := re.match(r"^(npm|pnpm|yarn|bun)", pm_field)
                ):
                    return match.group(1)  # type: ignore[return-value]
        except (json.JSONDecodeError, OSError, Exception):  # noqa: BLE001
            pass

        # Check what's available on the system (prefer faster ones)
        for manager in ("bun", "pnpm", "yarn", "npm"):
            if shutil.which(manager):
                return manager

        return "npm"

    async def get_tasks(self, fs: AsyncFileSystem, cwd: str) -> list[TaskInfo]:
        """Parse package.json and return available scripts."""
        config_file = await self.get_config_file(fs, cwd)
        if config_file is None:
            return []

        content = await self._read_file(fs, config_file)
        return self._parse_package_json(content)

    def _parse_package_json(self, content: str) -> list[TaskInfo]:
        """Parse package.json content to extract scripts."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict):
            return []

        tasks: list[TaskInfo] = []
        for name, command in scripts.items():
            description = command if isinstance(command, str) else None
            tasks.append(TaskInfo(name=name, description=description))

        return sorted(tasks, key=lambda t: t.name)

    def get_run_command(
        self,
        task_name: str,
        *args: str,
        package_manager: PackageManagerStr = "npm",
    ) -> list[str]:
        """Get the run command for a specific script.

        Args:
            task_name: Name of the script to run
            *args: Additional arguments to pass to the script
            package_manager: Which package manager to use
        """
        base_cmd = MANAGER_RUN_CMD.get(package_manager, ["npm", "run"])
        cmd = [*base_cmd, task_name]
        if args:
            # npm/pnpm/yarn need -- to pass args, bun doesn't
            if package_manager != "bun":
                cmd.append("--")
            cmd.extend(args)
        return cmd

    async def run_task(
        self,
        env: ExecutionEnvironment,
        task_name: str,
        *args: str,
        cwd: str | None = None,
        package_manager: PackageManagerStr | None = None,
    ) -> tuple[bool, str, str]:
        """Run a specific script using the execution environment.

        Args:
            env: Execution environment to run the command in
            task_name: Name of the script to run
            *args: Additional arguments to pass to the script
            cwd: Working directory (optional)
            package_manager: Override package manager detection
        """
        if package_manager is None:
            # Need filesystem for detection - get from env
            fs = env.get_fs()
            detect_cwd = cwd or "."
            package_manager = await self.detect_package_manager(fs, detect_cwd)

        cmd = self.get_run_command(task_name, *args, package_manager=package_manager)
        command_str = " ".join(cmd)
        if cwd:
            command_str = f"cd {cwd} && {command_str}"

        result = await env.execute_command(command_str)
        return (
            result.success,
            result.stdout or "",
            result.stderr or result.error or "",
        )

    def is_available(self) -> bool:
        """Check if any supported package manager is available."""
        return any(shutil.which(pm) for pm in ("npm", "pnpm", "yarn", "bun"))
