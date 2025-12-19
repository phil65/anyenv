"""LSP server definitions for Ruby."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, RootDetection


RUBOCOP = LSPServerInfo(
    id="rubocop",
    extensions=[".rb", ".rake", ".gemspec", ".ru"],
    root_detection=RootDetection(include_patterns=["Gemfile"]),
    command="rubocop",
    args=["--lsp"],
)
