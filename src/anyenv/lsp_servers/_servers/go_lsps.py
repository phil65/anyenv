"""LSP server definitions for various languages."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath
from typing import TYPE_CHECKING

from anyenv.lsp_servers._base import GoInstall, LSPServerInfo, RootDetection


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class GoplsServer(LSPServerInfo):
    """Go language server with go.work priority."""

    async def resolve_root(
        self,
        file_path: str,
        project_root: str,
        fs: AsyncFileSystem,
    ) -> str | None:
        """Prefer go.work over go.mod for workspace support."""
        # First check for go.work
        work_root = await self._find_nearest(
            posixpath.dirname(file_path),
            ["go.work"],
            project_root,
            fs,
        )
        if work_root:
            return posixpath.dirname(work_root)

        # Fall back to go.mod
        mod_root = await self._find_nearest(
            posixpath.dirname(file_path),
            ["go.mod", "go.sum"],
            project_root,
            fs,
        )
        return posixpath.dirname(mod_root) if mod_root else project_root


GOPLS = GoplsServer(
    id="gopls",
    extensions=[".go"],
    root_detection=RootDetection(
        include_patterns=["go.work", "go.mod", "go.sum"],
    ),
    command="gopls",
    args=[],
    go_install=GoInstall(package="golang.org/x/tools/gopls@latest"),
)
