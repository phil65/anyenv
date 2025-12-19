"""LSP server definitions for Java."""

from __future__ import annotations

from anyenv.lsp_servers._base import LSPServerInfo, RootDetection


JDTLS = LSPServerInfo(
    id="jdtls",
    extensions=[".java"],
    root_detection=RootDetection(
        include_patterns=[
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            ".project",
            ".classpath",
        ],
    ),
    command="jdtls",
    args=[],
)
