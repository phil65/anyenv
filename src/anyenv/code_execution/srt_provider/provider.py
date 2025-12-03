"""Sandboxed execution environment using Anthropic's sandbox-runtime."""

from __future__ import annotations

import atexit
import json
from pathlib import Path
import shlex
import tempfile
from typing import TYPE_CHECKING

from anyenv.code_execution.local_provider import LocalExecutionEnvironment
from anyenv.code_execution.srt_provider.config import SandboxConfig


if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from upathtools.filesystems.sandbox_filesystems import SRTFS

    from anyenv.code_execution.models import Language, ServerInfo


class SRTExecutionEnvironment(LocalExecutionEnvironment):
    """Sandboxed local execution using Anthropic's sandbox-runtime (srt).

    This provider wraps commands with `srt` to enforce:
    - Network restrictions (domain allowlist/denylist)
    - Filesystem read restrictions (deny specific paths)
    - Filesystem write restrictions (allow specific paths only)

    Requires `srt` CLI to be installed: `npm install -g @anthropic-ai/sandbox-runtime`
    """

    def __init__(
        self,
        sandbox_config: SandboxConfig | None = None,
        *,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        timeout: float = 30.0,
        executable: str | None = None,
        language: Language = "python",
    ) -> None:
        """Initialize sandboxed execution environment.

        Args:
            sandbox_config: Sandbox restrictions configuration
            lifespan_handler: Async context manager for tool server
            dependencies: List of packages to install
            timeout: Execution timeout in seconds
            executable: Executable to use (auto-detect if None)
            language: Programming language
        """
        # Force isolated mode - sandbox only works with subprocess
        super().__init__(
            lifespan_handler=lifespan_handler,
            dependencies=dependencies,
            timeout=timeout,
            isolated=True,
            executable=executable,
            language=language,
        )
        self.sandbox_config = sandbox_config or SandboxConfig()
        self._settings_file = self._create_settings_file()
        atexit.register(self._cleanup_settings_file)

    def get_fs(self) -> SRTFS:
        """Get sandboxed filesystem."""
        from upathtools.filesystems.sandbox_filesystems import SRTFS

        return SRTFS(
            allowed_domains=self.sandbox_config.allowed_domains,
            denied_domains=self.sandbox_config.denied_domains,
            allow_unix_sockets=self.sandbox_config.allow_unix_sockets,
            allow_all_unix_sockets=self.sandbox_config.allow_all_unix_sockets,
            allow_local_binding=self.sandbox_config.allow_local_binding,
            deny_read=self.sandbox_config.deny_read,
            allow_write=self.sandbox_config.allow_write,
            deny_write=self.sandbox_config.deny_write,
            timeout=self.timeout,
        )

    def _create_settings_file(self) -> Path:
        """Create temporary srt settings file."""
        settings = self.sandbox_config.to_srt_settings()
        _fd, path = tempfile.mkstemp(suffix=".json", prefix="srt-settings-")
        path = Path(path)
        path.write_text(json.dumps(settings, indent=2))
        return path

    def _cleanup_settings_file(self) -> None:
        """Remove temporary settings file."""
        if self._settings_file.exists():
            self._settings_file.unlink()

    def wrap_command(self, command: str) -> str:
        """Wrap command with srt sandbox."""
        return shlex.join(["srt", "--settings", str(self._settings_file), command])
