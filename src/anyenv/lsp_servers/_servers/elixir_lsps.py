"""LSP server definitions for various languages."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, RootDetection


ELIXIR_LS = LSPServerInfo(
    id="elixir-ls",
    extensions=[".ex", ".exs"],
    root_detection=RootDetection(include_patterns=["mix.exs", "mix.lock"]),
    command="elixir-ls",
    args=[],
)
