"""LSP server definitions for Swift / Objective-C."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, RootDetection


SOURCEKIT_LSP = LSPServerInfo(
    id="sourcekit-lsp",
    extensions=[".swift", ".objc", ".objcpp"],
    root_detection=RootDetection(
        include_patterns=["Package.swift", "*.xcodeproj", "*.xcworkspace"],
    ),
    command="sourcekit-lsp",
    args=[],
)
