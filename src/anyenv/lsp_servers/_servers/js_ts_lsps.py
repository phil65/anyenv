"""LSP server definitions for JS/TS."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]

from anyenv.lsp_servers._base import LSPServerInfo, NpmInstall, RootDetection


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
