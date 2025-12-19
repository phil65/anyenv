"""LSP server definitions for C#."""

from __future__ import annotations

from anyenv.lsp_servers._base import DotnetInstall, LSPServerInfo, RootDetection


CSHARP_LS = LSPServerInfo(
    id="csharp-ls",
    extensions=[".cs"],
    root_detection=RootDetection(
        include_patterns=[".sln", ".csproj", "global.json"],
    ),
    command="csharp-ls",
    args=[],
    dotnet_install=DotnetInstall(package="csharp-ls"),
)
