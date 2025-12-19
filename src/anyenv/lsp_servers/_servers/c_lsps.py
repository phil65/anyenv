"""LSP server definitions for C / C++."""

from __future__ import annotations

from anyenv.lsp_servers._base import GitHubRelease, LSPServerInfo, RootDetection


CLANGD = LSPServerInfo(
    id="clangd",
    extensions=[".c", ".cpp", ".cc", ".cxx", ".c++", ".h", ".hpp", ".hh", ".hxx", ".h++"],
    root_detection=RootDetection(
        include_patterns=[
            "compile_commands.json",
            "compile_flags.txt",
            ".clangd",
            "CMakeLists.txt",
            "Makefile",
        ],
    ),
    command="clangd",
    args=["--background-index", "--clang-tidy"],
    github_release=GitHubRelease(
        repo="clangd/clangd",
        asset_pattern="clangd-{platform}-{version}.{ext}",
        binary_name="clangd",
        extract_subdir="clangd_{version}/bin",
    ),
)
