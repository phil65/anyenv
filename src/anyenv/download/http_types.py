"""Types for HTTP requests and downloads."""

from __future__ import annotations

from collections.abc import Mapping


HeaderType = dict[str, str]
ParamsType = Mapping[str, str | int | float | None]
