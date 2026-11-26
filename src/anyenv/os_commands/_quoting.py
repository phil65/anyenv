"""Quoting for the generated shell and PowerShell commands.

Paths and names come from users and agents: they must reach the command as literals,
never as shell syntax (`$(...)`, quotes, `~`, a leading `-`).
"""

import base64
import re
import shlex


POWERSHELL_PREFIX = "powershell -NoProfile -EncodedCommand "
# An encoded command reports progress (e.g. "Preparing modules for first use") as
# CLIXML on stderr, which a terminal merges into the output the commands parse.
_QUIET = "$ProgressPreference = 'SilentlyContinue'; "
# PowerShell treats the typographic single quotes like ' too.
_PS_SINGLE_QUOTES = re.compile("['\u2018\u2019\u201a\u201b]")


def sh_quote(value: str) -> str:
    """Quote a value as one literal word for a POSIX shell."""
    return shlex.quote(value)


def sh_path(path: str) -> str:
    """Quote a path operand; a leading `-` gets `./` so no tool reads it as an option."""
    return shlex.quote(f"./{path}" if path.startswith("-") else path)


def ps_literal(value: str) -> str:
    """Quote a value as a PowerShell single-quoted (verbatim) string literal."""
    return "'" + _PS_SINGLE_QUOTES.sub(lambda m: m.group(0) * 2, value) + "'"


def powershell(script: str) -> str:
    """Wrap a PowerShell script in a command line no outer shell can reinterpret.

    The script travels base64-encoded (UTF-16LE), so neither cmd.exe nor an outer
    PowerShell expands `%VAR%`, `$(...)` or quotes in it. Progress output is off.
    """
    encoded = base64.b64encode((_QUIET + script).encode("utf-16-le")).decode("ascii")
    return POWERSHELL_PREFIX + encoded


def powershell_script(command: str) -> str | None:
    """The script of a command made by `powershell`, else None."""
    if not command.startswith(POWERSHELL_PREFIX):
        return None
    script = base64.b64decode(command.removeprefix(POWERSHELL_PREFIX)).decode("utf-16-le")
    return script.removeprefix(_QUIET)
