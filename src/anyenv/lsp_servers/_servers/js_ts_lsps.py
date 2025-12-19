"""LSP server definitions for JS/TS."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]

from anyenv.lsp_servers._base import (
    CLIDiagnosticConfig,
    Diagnostic,
    LSPServerInfo,
    NpmInstall,
    RootDetection,
    severity_from_string,
)


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
class OxlintServer(LSPServerInfo):
    """Oxlint (oxc) linter with JSON diagnostic parsing."""

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse oxlint JSON output."""
        import anyenv

        diagnostics: list[Diagnostic] = []

        try:
            data = anyenv.load_json(output, return_type=dict)
            for diag in data.get("diagnostics", []):
                # Get location from labels
                labels = diag.get("labels", [])
                if labels:
                    span = labels[0].get("span", {})
                    line = span.get("line", 1)
                    column = span.get("column", 1)
                else:
                    line, column = 1, 1

                diagnostics.append(
                    Diagnostic(
                        file=diag.get("filename", ""),
                        line=line,
                        column=column,
                        severity=severity_from_string(diag.get("severity", "warning")),
                        message=diag.get("message", ""),
                        code=diag.get("code"),
                        source=self.id,
                    )
                )
        except anyenv.JsonLoadError:
            pass

        return diagnostics


@dataclass
class BiomeServer(LSPServerInfo):
    """Biome linter/formatter with JSON diagnostic parsing."""

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse biome JSON output."""
        import anyenv

        diagnostics: list[Diagnostic] = []

        try:
            # Find JSON in output (biome may print extra text)
            json_start = output.find("{")
            if json_start == -1:
                return diagnostics

            data = anyenv.load_json(output[json_start:], return_type=dict)
            for diag in data.get("diagnostics", []):
                location = diag.get("location", {})
                span = location.get("span", [0, 0])
                # Biome uses byte offsets, not line/column directly
                # For now, use offset as approximation (would need source to convert)
                path_info = location.get("path", {})
                file_path = path_info.get("file", "") if isinstance(path_info, dict) else ""

                diagnostics.append(
                    Diagnostic(
                        file=file_path,
                        line=1,  # Would need source text to calculate
                        column=span[0] if span else 1,
                        severity=severity_from_string(diag.get("severity", "error")),
                        message=diag.get("description", ""),
                        code=diag.get("category"),
                        source=self.id,
                    )
                )
        except anyenv.JsonLoadError:
            pass

        return diagnostics


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

OXLINT = OxlintServer(
    id="oxlint",
    extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue"],
    root_detection=RootDetection(
        include_patterns=[
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
            ".oxlintrc.json",
        ],
    ),
    command="oxlint",  # No LSP server mode, CLI only
    args=[],
    cli_diagnostics=CLIDiagnosticConfig(
        command="oxlint",
        args=["--format", "json", "{files}"],
        output_format="json",
    ),
)

BIOME = BiomeServer(
    id="biome",
    extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".json", ".jsonc"],
    root_detection=RootDetection(
        include_patterns=[
            "biome.json",
            "biome.jsonc",
            "package-lock.json",
            "bun.lockb",
            "bun.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
        ],
    ),
    command="biome",
    args=["lsp-proxy"],
    cli_diagnostics=CLIDiagnosticConfig(
        command="biome",
        args=["lint", "--reporter=json", "{files}"],
        output_format="json",
    ),
)
