"""LSP server definitions for Lua."""

from __future__ import annotations

from anyenv.lsp_servers._base import GitHubRelease, LSPServerInfo, RootDetection


LUA_LS = LSPServerInfo(
    id="lua-ls",
    extensions=[".lua"],
    root_detection=RootDetection(
        include_patterns=[
            ".luarc.json",
            ".luarc.jsonc",
            ".luacheckrc",
            ".stylua.toml",
            "stylua.toml",
            "selene.toml",
            "selene.yml",
        ],
    ),
    command="lua-language-server",
    args=[],
    github_release=GitHubRelease(
        repo="LuaLS/lua-language-server",
        asset_pattern="lua-language-server-{version}-{platform}-{arch}.{ext}",
        binary_name="lua-language-server",
        extract_subdir="bin",
    ),
)
