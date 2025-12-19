"""LSP server definitions for YAML."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, NpmInstall, RootDetection


YAML_LS = LSPServerInfo(
    id="yaml-ls",
    extensions=[".yaml", ".yml"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="yaml-language-server",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="yaml-language-server",
        entry_path="yaml-language-server/out/server/src/server.js",
    ),
)
