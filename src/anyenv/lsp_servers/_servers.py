"""LSP server definitions for various languages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import posixpath
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]

from anyenv.lsp_servers._base import (
    CLIDiagnosticConfig,
    Diagnostic,
    DotnetInstall,
    GitHubRelease,
    GoInstall,
    LSPServerInfo,
    NpmInstall,
    RootDetection,
    severity_from_string,
)


# Custom server classes for complex behaviors


@dataclass
class RustAnalyzerServer(LSPServerInfo):
    """Rust analyzer with workspace detection."""

    async def resolve_root(
        self,
        file_path: str,
        project_root: str,
        fs: AsyncFileSystem,
    ) -> str | None:
        """Walk up to find workspace root containing [workspace] in Cargo.toml."""
        crate_root = await super().resolve_root(file_path, project_root, fs)
        if crate_root is None:
            return None

        # Walk up looking for workspace
        current = crate_root.rstrip("/")
        project_root = project_root.rstrip("/")

        while True:
            cargo_toml = posixpath.join(current, "Cargo.toml")
            try:
                if await fs._exists(cargo_toml):  # noqa: SLF001
                    content = (await fs._cat_file(cargo_toml)).decode()  # noqa: SLF001
                    if "[workspace]" in content:
                        return current
            except Exception:  # noqa: BLE001
                pass

            if current == project_root:
                break
            parent = posixpath.dirname(current)
            if current in (parent, fs.root_marker):
                break
            current = parent

        return crate_root


@dataclass
class PyrightServer(LSPServerInfo):
    """Pyright with virtualenv detection and JSON diagnostic parsing."""

    async def resolve_initialization(self, root: str, fs: AsyncFileSystem) -> dict[str, Any]:
        """Detect virtualenv and set pythonPath."""
        init = await super().resolve_initialization(root, fs)

        venv_candidates = [
            os.environ.get("VIRTUAL_ENV"),
            posixpath.join(root, ".venv"),
            posixpath.join(root, "venv"),
        ]

        for venv_path in venv_candidates:
            if venv_path is None:
                continue
            if os.name == "nt":
                python = posixpath.join(venv_path, "Scripts", "python.exe")
            else:
                python = posixpath.join(venv_path, "bin", "python")
            try:
                if await fs._exists(python):  # noqa: SLF001
                    init["pythonPath"] = python
                    break
            except Exception:  # noqa: BLE001
                pass

        return init

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse pyright JSON output."""
        diagnostics: list[Diagnostic] = []

        try:
            # Find JSON object in output (may have warnings before it)
            json_start = output.find("{")
            if json_start == -1:
                return diagnostics
            data = json.loads(output[json_start:])

            for diag in data.get("generalDiagnostics", []):
                range_info = diag.get("range", {})
                start = range_info.get("start", {})
                end = range_info.get("end", {})

                diagnostics.append(
                    Diagnostic(
                        file=diag.get("file", ""),
                        line=start.get("line", 0) + 1,  # pyright uses 0-indexed
                        column=start.get("character", 0) + 1,
                        end_line=end.get("line", start.get("line", 0)) + 1,
                        end_column=end.get("character", start.get("character", 0)) + 1,
                        severity=severity_from_string(diag.get("severity", "error")),
                        message=diag.get("message", ""),
                        code=diag.get("rule"),
                        source=self.id,
                    )
                )
        except json.JSONDecodeError:
            pass

        return diagnostics


@dataclass
class MypyServer(LSPServerInfo):
    """Mypy with JSON diagnostic parsing."""

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse mypy JSON output (one JSON object per line)."""
        diagnostics: list[Diagnostic] = []

        for line in output.strip().splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                diagnostics.append(
                    Diagnostic(
                        file=data.get("file", ""),
                        line=data.get("line", 1),
                        column=data.get("column", 1),
                        severity=severity_from_string(data.get("severity", "error")),
                        message=data.get("message", ""),
                        code=data.get("code"),
                        source=self.id,
                    )
                )
            except json.JSONDecodeError:
                continue

        return diagnostics


@dataclass
class TypeScriptServer(LSPServerInfo):
    """TypeScript language server with tsserver path detection."""

    async def resolve_initialization(self, root: str, fs: AsyncFileSystem) -> dict[str, Any]:
        """Detect tsserver.js path."""
        init = await super().resolve_initialization(root, fs)

        tsserver = posixpath.join(root, "node_modules", "typescript", "lib", "tsserver.js")
        try:
            if await fs._exists(tsserver):  # noqa: SLF001
                init["tsserver"] = {"path": tsserver}
        except Exception:  # noqa: BLE001
            pass

        return init


@dataclass
class AstroServer(LSPServerInfo):
    """Astro language server with TypeScript SDK detection."""

    async def resolve_initialization(self, root: str, fs: AsyncFileSystem) -> dict[str, Any]:
        """Detect TypeScript SDK path for Astro."""
        init = await super().resolve_initialization(root, fs)

        tsserver = posixpath.join(root, "node_modules", "typescript", "lib", "tsserver.js")
        try:
            if await fs._exists(tsserver):  # noqa: SLF001
                init["typescript"] = {"tsdk": posixpath.dirname(tsserver)}
        except Exception:  # noqa: BLE001
            pass

        return init


@dataclass
class GoplsServer(LSPServerInfo):
    """Go language server with go.work priority."""

    async def resolve_root(
        self,
        file_path: str,
        project_root: str,
        fs: AsyncFileSystem,
    ) -> str | None:
        """Prefer go.work over go.mod for workspace support."""
        # First check for go.work
        work_root = await self._find_nearest(
            posixpath.dirname(file_path),
            ["go.work"],
            project_root,
            fs,
        )
        if work_root:
            return posixpath.dirname(work_root)

        # Fall back to go.mod
        mod_root = await self._find_nearest(
            posixpath.dirname(file_path),
            ["go.mod", "go.sum"],
            project_root,
            fs,
        )
        return posixpath.dirname(mod_root) if mod_root else project_root


# JavaScript/TypeScript ecosystem

DENO = LSPServerInfo(
    id="deno",
    extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs"],
    root_detection=RootDetection(include_patterns=["deno.json", "deno.jsonc"]),
    command="deno",
    args=["lsp"],
)

TYPESCRIPT = TypeScriptServer(
    id="typescript",
    extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
        exclude_patterns=["deno.json", "deno.jsonc"],
    ),
    command="typescript-language-server",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="typescript-language-server",
        entry_path="typescript-language-server/lib/cli.mjs",
    ),
)

VUE = LSPServerInfo(
    id="vue",
    extensions=[".vue"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="vue-language-server",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="@vue/language-server",
        entry_path="@vue/language-server/bin/vue-language-server.js",
    ),
)

SVELTE = LSPServerInfo(
    id="svelte",
    extensions=[".svelte"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="svelteserver",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="svelte-language-server",
        entry_path="svelte-language-server/bin/server.js",
    ),
)

ASTRO = AstroServer(
    id="astro",
    extensions=[".astro"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="astro-ls",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="@astrojs/language-server",
        entry_path="@astrojs/language-server/bin/nodeServer.js",
    ),
)

ESLINT = LSPServerInfo(
    id="eslint",
    extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="vscode-eslint-language-server",
    args=["--stdio"],
)

# Python

PYRIGHT = PyrightServer(
    id="pyright",
    extensions=[".py", ".pyi"],
    root_detection=RootDetection(
        include_patterns=[
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
            "pyrightconfig.json",
        ],
    ),
    command="pyright-langserver",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="pyright",
        entry_path="pyright/dist/pyright-langserver.js",
    ),
    cli_diagnostics=CLIDiagnosticConfig(
        command="pyright",
        args=["--outputjson", "{files}"],
        output_format="json",
    ),
)

BASEDPYRIGHT = PyrightServer(
    id="basedpyright",
    extensions=[".py", ".pyi"],
    root_detection=RootDetection(
        include_patterns=[
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
            "pyrightconfig.json",
        ],
    ),
    command="basedpyright-langserver",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="basedpyright",
        entry_path="basedpyright/dist/pyright-langserver.js",
    ),
    cli_diagnostics=CLIDiagnosticConfig(
        command="basedpyright",
        args=["--outputjson", "{files}"],
        output_format="json",
    ),
)

MYPY = MypyServer(
    id="mypy",
    extensions=[".py", ".pyi"],
    root_detection=RootDetection(
        include_patterns=[
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "mypy.ini",
            ".mypy.ini",
        ],
    ),
    command="dmypy",
    args=["run", "--"],
    cli_diagnostics=CLIDiagnosticConfig(
        command="mypy",
        args=["--output", "json", "{files}"],
        output_format="json",
    ),
)

# Go

GOPLS = GoplsServer(
    id="gopls",
    extensions=[".go"],
    root_detection=RootDetection(
        include_patterns=["go.work", "go.mod", "go.sum"],
    ),
    command="gopls",
    args=[],
    go_install=GoInstall(package="golang.org/x/tools/gopls@latest"),
)

# Rust

RUST_ANALYZER = RustAnalyzerServer(
    id="rust-analyzer",
    extensions=[".rs"],
    root_detection=RootDetection(
        include_patterns=["Cargo.toml", "Cargo.lock"],
        workspace_marker="[workspace]",
    ),
    command="rust-analyzer",
    args=[],
)

# Zig

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

# C/C++

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

# C#

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

# Ruby

RUBOCOP = LSPServerInfo(
    id="rubocop",
    extensions=[".rb", ".rake", ".gemspec", ".ru"],
    root_detection=RootDetection(include_patterns=["Gemfile"]),
    command="rubocop",
    args=["--lsp"],
)

# Elixir

ELIXIR_LS = LSPServerInfo(
    id="elixir-ls",
    extensions=[".ex", ".exs"],
    root_detection=RootDetection(include_patterns=["mix.exs", "mix.lock"]),
    command="elixir-ls",
    args=[],
)

# Swift/Objective-C

SOURCEKIT_LSP = LSPServerInfo(
    id="sourcekit-lsp",
    extensions=[".swift", ".objc", ".objcpp"],
    root_detection=RootDetection(
        include_patterns=["Package.swift", "*.xcodeproj", "*.xcworkspace"],
    ),
    command="sourcekit-lsp",
    args=[],
)

# Java

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

# YAML

YAML_LS = LSPServerInfo(
    id="yaml-ls",
    extensions=[".yaml", ".yml"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="yaml-language-server",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="yaml-language-server",
        entry_path="yaml-language-server/out/server/src/server.js",
    ),
)

# Lua

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

# PHP

PHP_INTELEPHENSE = LSPServerInfo(
    id="intelephense",
    extensions=[".php"],
    root_detection=RootDetection(
        include_patterns=["composer.json", "composer.lock", ".php-version"],
    ),
    command="intelephense",
    args=["--stdio"],
    npm_install=NpmInstall(
        package="intelephense",
        entry_path="intelephense/lib/intelephense.js",
    ),
)

# Dart

DART = LSPServerInfo(
    id="dart",
    extensions=[".dart"],
    root_detection=RootDetection(
        include_patterns=["pubspec.yaml", "analysis_options.yaml"],
    ),
    command="dart",
    args=["language-server", "--lsp"],
)

# All servers
ALL_SERVERS: list[LSPServerInfo] = [
    # JavaScript/TypeScript
    DENO,
    TYPESCRIPT,
    VUE,
    SVELTE,
    ASTRO,
    ESLINT,
    # Python
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
