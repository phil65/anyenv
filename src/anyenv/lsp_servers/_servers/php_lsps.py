"""LSP server definitions for PHP."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, NpmInstall, RootDetection


PHP_INTELEPHENSE = LSPServerInfo(
    id="intelephense",
    extensions=[".php"],
    root_detection=RootDetection(
        include_patterns=["composer.json", "composer.lock", ".php-version"],
    ),
    command="intelephense",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="intelephense",
        entry_path="intelephense/lib/intelephense.js",
    ),
)
