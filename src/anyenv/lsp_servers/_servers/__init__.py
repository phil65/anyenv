"""LSP server definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .js_ts_lsps import (
    DENO,
    TYPESCRIPT,
    VUE,
    SVELTE,
    ASTRO,
    ESLINT,
    OXLINT,
    BIOME,
    AstroServer,
    TypeScriptServer,
)
from .python_lsps import TY, ZUBAN, PYREFLY, PYRIGHT, BASEDPYRIGHT, MYPY, PyrightServer, MypyServer
from .rust_lsps import RUST_ANALYZER, RustAnalyzerServer
from .go_lsps import GOPLS, GoplsServer
from .c_lsps import CLANGD
from .zig_lsps import ZLS
from .ruby_lsps import RUBOCOP
from .lua_lsps import LUA_LS
from .swift_lsps import SOURCEKIT_LSP
from .elixir_lsps import ELIXIR_LS
from .php_lsps import PHP_INTELEPHENSE
from .dart_lsps import DART
from .yaml_lsps import YAML_LS
from .c_sharp_lsps import CSHARP_LS
from .java_lsps import JDTLS

if TYPE_CHECKING:
    from anyenv.lsp_servers._base import LSPServerInfo


__all__ = [
    # Server instances
    "ALL_SERVERS",
    "ASTRO",
    "BASEDPYRIGHT",
    "BIOME",
    "CLANGD",
    "CSHARP_LS",
    "DART",
    "DENO",
    "ELIXIR_LS",
    "ESLINT",
    "GOPLS",
    "JDTLS",
    "LUA_LS",
    "MYPY",
    "OXLINT",
    "PHP_INTELEPHENSE",
    "PYREFLY",
    "PYRIGHT",
    "RUBOCOP",
    "RUST_ANALYZER",
    "SOURCEKIT_LSP",
    "SVELTE",
    "TY",
    "TYPESCRIPT",
    "VUE",
    "YAML_LS",
    "ZLS",
    "ZUBAN",
    # Server classes
    "AstroServer",
    "GoplsServer",
    "MypyServer",
    "PyrightServer",
    "RustAnalyzerServer",
    "TypeScriptServer",
]

# All servers
ALL_SERVERS: list[LSPServerInfo] = [
    # JavaScript/TypeScript
    OXLINT,
    BIOME,
    DENO,
    TYPESCRIPT,
    VUE,
    SVELTE,
    ASTRO,
    ESLINT,
    # Python
    TY,
    ZUBAN,
    PYREFLY,
    PYRIGHT,
    BASEDPYRIGHT,
    MYPY,
    # Go
    GOPLS,
    # Rust
    RUST_ANALYZER,
    # Zig
    ZLS,
    # C/C++
    CLANGD,
    # C#
    CSHARP_LS,
    # Ruby
    RUBOCOP,
    # Elixir
    ELIXIR_LS,
    # Swift
    SOURCEKIT_LSP,
    # Java
    JDTLS,
    # YAML
    YAML_LS,
    # Lua
    LUA_LS,
    # PHP
    PHP_INTELEPHENSE,
    # Dart
    DART,
]
