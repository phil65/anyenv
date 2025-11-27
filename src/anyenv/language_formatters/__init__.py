"""Language formatters with anyenv execution environments."""

from anyenv.language_formatters._base import (
    FormatAndLintResult,
    FormatResult,
    LanguageFormatter,
    LintResult,
)
from anyenv.language_formatters._elixir import ElixirFormatter
from anyenv.language_formatters._jvm import KtlintFormatter
from anyenv.language_formatters._python import PythonRuffFormatter, PythonUvFormatter
from anyenv.language_formatters._r import AirFormatter
from anyenv.language_formatters._registry import FormatterRegistry
from anyenv.language_formatters._ruby import RubocopFormatter, StandardRBFormatter
from anyenv.language_formatters._systems import (
    ClangFormatFormatter,
    GoFormatter,
    RustFormatter,
    ZigFormatter,
)
from anyenv.language_formatters._toml import TOMLFormatter
from anyenv.language_formatters._web import (
    BiomeFormatter,
    HtmlBeautifierFormatter,
    PrettierFormatter,
)

# Backwards compatibility aliases
PythonFormatter = PythonUvFormatter
TypeScriptFormatter = BiomeFormatter

__all__ = [
    # Other languages
    "AirFormatter",
    # Web
    "BiomeFormatter",
    # Systems
    "ClangFormatFormatter",
    "ElixirFormatter",
    # Base classes and results
    "FormatAndLintResult",
    "FormatResult",
    # Registry
    "FormatterRegistry",
    "GoFormatter",
    "HtmlBeautifierFormatter",
    # JVM
    "KtlintFormatter",
    "LanguageFormatter",
    "LintResult",
    "PrettierFormatter",
    # Python
    "PythonFormatter",
    "PythonRuffFormatter",
    "PythonUvFormatter",
    # Ruby
    "RubocopFormatter",
    "RustFormatter",
    "StandardRBFormatter",
    "TOMLFormatter",
    "TypeScriptFormatter",
    "ZigFormatter",
]
