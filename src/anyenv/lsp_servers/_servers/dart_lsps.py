"""LSP server definitions for Dart."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, RootDetection


DART = LSPServerInfo(
    id="dart",
    extensions=[".dart"],
    root_detection=RootDetection(
        include_patterns=["pubspec.yaml", "analysis_options.yaml"],
    ),
    command="dart",
    args=["language-server", "--lsp"],
)
