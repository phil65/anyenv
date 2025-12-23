"""LSP server definitions for various languages."""

from __future__ import annotations

from dataclasses import dataclass
import os
import posixpath
from typing import TYPE_CHECKING, Any

from anyenv.lsp_servers._base import (
    CLIDiagnosticConfig,
    Diagnostic,
    LSPServerInfo,
    NpmInstall,
    RootDetection,
    severity_from_string,
)


if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]


# Custom server classes for complex behaviors
def get_python_venv_candidates(root: str) -> list[str]:
    paths = [
        os.environ.get("VIRTUAL_ENV"),
        posixpath.join(root, ".venv"),
        posixpath.join(root, "venv"),
    ]
    return [i for i in paths if i is not None]


@dataclass
class PyrightServer(LSPServerInfo):
    """Pyright with virtualenv detection and JSON diagnostic parsing."""

    async def resolve_initialization(self, root: str, fs: AsyncFileSystem) -> dict[str, Any]:
        """Detect virtualenv and set pythonPath."""
        init = await super().resolve_initialization(root, fs)

        for venv_path in get_python_venv_candidates(root):
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
        import anyenv

        diagnostics: list[Diagnostic] = []

        try:
            # Find JSON object in output (may have warnings before it)
            json_start = output.find("{")
            if json_start == -1:
                return diagnostics
            data = anyenv.load_json(output[json_start:], return_type=dict)

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
        except anyenv.JsonLoadError:
            pass

        return diagnostics


@dataclass
class ZubanServer(LSPServerInfo):
    """Zuban type checker with mypy-compatible text output parsing."""

    def _parse_text_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse zuban mypy-compatible text output.

        Format: file.py:line:column: severity: message  [error-code]
        """
        import re

        diagnostics: list[Diagnostic] = []
        # Pattern: path:line:col: severity: message  [code]
        pattern = re.compile(
            r"^(.+?):(\d+):(\d+): (error|warning|note): (.+?)(?:\s+\[([^\]]+)\])?$"
        )

        for line in output.strip().splitlines():
            line = line.strip()
            if match := pattern.match(line):
                file_path, line_no, col, severity, message, code = match.groups()
                diagnostics.append(
                    Diagnostic(
                        file=file_path,
                        line=int(line_no),
                        column=int(col),
                        severity=severity_from_string(severity),
                        message=message.strip(),
                        code=code,
                        source=self.id,
                    )
                )

        return diagnostics

    def parse_diagnostics(self, stdout: str, stderr: str) -> list[Diagnostic]:
        """Parse diagnostics from CLI output."""
        return self._parse_text_diagnostics(stdout or stderr)


@dataclass
class TyServer(LSPServerInfo):
    """Ty (Astral) type checker with GitLab JSON diagnostic parsing."""

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse ty GitLab JSON output."""
        import anyenv

        diagnostics: list[Diagnostic] = []

        try:
            data = anyenv.load_json(output, return_type=list)
            for item in data:
                location = item.get("location", {})
                positions = location.get("positions", {})
                begin = positions.get("begin", {})
                end = positions.get("end", {})

                # Map GitLab severity to our severity
                gitlab_severity = item.get("severity", "major")
                if gitlab_severity in ("blocker", "critical", "major"):
                    severity = "error"
                elif gitlab_severity == "minor":
                    severity = "warning"
                else:
                    severity = "information"

                diagnostics.append(
                    Diagnostic(
                        file=location.get("path", ""),
                        line=begin.get("line", 1),
                        column=begin.get("column", 1),
                        end_line=end.get("line", begin.get("line", 1)),
                        end_column=end.get("column", begin.get("column", 1)),
                        severity=severity_from_string(severity),
                        message=item.get("description", ""),
                        code=item.get("check_name"),
                        source=self.id,
                    )
                )
        except anyenv.JsonLoadError:
            pass

        return diagnostics


@dataclass
class PyreflyServer(LSPServerInfo):
    """Pyrefly (Meta) type checker with JSON diagnostic parsing."""

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse pyrefly JSON output."""
        import anyenv

        diagnostics: list[Diagnostic] = []

        try:
            # Find JSON object (may have INFO line after it)
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                return diagnostics

            data = anyenv.load_json(output[json_start:json_end], return_type=dict)
            for error in data.get("errors", []):
                diagnostics.append(  # noqa: PERF401
                    Diagnostic(
                        file=error.get("path", ""),
                        line=error.get("line", 1),
                        column=error.get("column", 1),
                        end_line=error.get("stop_line", error.get("line", 1)),
                        end_column=error.get("stop_column", error.get("column", 1)),
                        severity=severity_from_string(error.get("severity", "error")),
                        message=error.get("description", ""),
                        code=error.get("name"),
                        source=self.id,
                    )
                )
        except anyenv.JsonLoadError:
            pass

        return diagnostics


@dataclass
class MypyServer(LSPServerInfo):
    """Mypy with JSON diagnostic parsing."""

    def _parse_json_diagnostics(self, output: str) -> list[Diagnostic]:
        """Parse mypy JSON output (one JSON object per line)."""
        import anyenv

        diagnostics: list[Diagnostic] = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                data = anyenv.load_json(line, return_type=dict)
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
            except anyenv.JsonLoadError:
                continue

        return diagnostics


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

ZUBAN = ZubanServer(
    id="zuban",
    extensions=[".py", ".pyi"],
    root_detection=RootDetection(
        include_patterns=[
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "mypy.ini",
            ".mypy.ini",
        ],
    ),
    command="zuban",
    args=["server"],
    cli_diagnostics=CLIDiagnosticConfig(
        command="zuban",
        args=["check", "--show-column-numbers", "--show-error-codes", "{files}"],
        output_format="text",
    ),
)

TY = TyServer(
    id="ty",
    extensions=[".py", ".pyi"],
    root_detection=RootDetection(
        include_patterns=[
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "ty.toml",
        ],
    ),
    command="ty",
    args=["server"],
    cli_diagnostics=CLIDiagnosticConfig(
        command="ty",
        args=["check", "--output-format", "gitlab", "{files}"],
        output_format="json",
    ),
)

PYREFLY = PyreflyServer(
    id="pyrefly",
    extensions=[".py", ".pyi"],
    root_detection=RootDetection(
        include_patterns=[
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "pyrefly.toml",
        ],
    ),
    command="pyrefly",
    args=["lsp"],
    cli_diagnostics=CLIDiagnosticConfig(
        command="pyrefly",
        args=["check", "--output-format", "json", "{files}"],
        output_format="json",
    ),
)
