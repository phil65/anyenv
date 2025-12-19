"""LSP server definitions for Rust."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath
from typing import TYPE_CHECKING

from anyenv.lsp_servers._base import LSPServerInfo, RootDetection


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


@dataclass
class RustAnalyzerServer(LSPServerInfo):
    """Rust analyzer with workspace detection."""

    async def resolve_root(
        self,
        file_path: str,
        project_root: str,
        fs: AsyncFileSystem,
    ) -> str | None:
        """Walk up to find workspace root containing [workspace] in Cargo.toml."""
        crate_root = await super().resolve_root(file_path, project_root, fs)
        if crate_root is None:
            return None

        # Walk up looking for workspace
        current = crate_root.rstrip("/")
        project_root = project_root.rstrip("/")

        while True:
            cargo_toml = posixpath.join(current, "Cargo.toml")
            try:
                if await fs._exists(cargo_toml):  # noqa: SLF001
                    content = (await fs._cat_file(cargo_toml)).decode()  # noqa: SLF001
                    if "[workspace]" in content:
                        return current
            except Exception:  # noqa: BLE001
                pass

            if current == project_root:
                break
            parent = posixpath.dirname(current)
            if current in (parent, fs.root_marker):
                break
            current = parent

        return crate_root


RUST_ANALYZER = RustAnalyzerServer(
    id="rust-analyzer",
    extensions=[".rs"],
    root_detection=RootDetection(
        include_patterns=["Cargo.toml", "Cargo.lock"],
        workspace_marker="[workspace]",
    ),
    command="rust-analyzer",
    args=[],
)
