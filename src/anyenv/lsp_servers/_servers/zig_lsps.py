"""LSP server definitions for Zig."""

from __future__ import annotations

from anyenv.lsp_servers._base import GitHubRelease, LSPServerInfo, RootDetection


ZLS = LSPServerInfo(
    id="zls",
    extensions=[".zig", ".zon"],
    root_detection=RootDetection(include_patterns=["build.zig"]),
    command="zls",
    args=[],
    github_release=GitHubRelease(
        repo="zigtools/zls",
        asset_pattern="zls-{arch}-{platform}.{ext}",
        binary_name="zls",
    ),
)
