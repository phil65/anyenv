"""Tests for validate_json_data."""

from __future__ import annotations

from typing import Literal, TypedDict

import pytest

from anyenv import validate


class Info(TypedDict):
    """Sample TypedDict."""

    name: str


@pytest.fixture(params=[True, False], ids=["pydantic", "no-pydantic"])
def pydantic_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Run with and without Pydantic validation."""
    monkeypatch.setattr(validate, "_has_pydantic", request.param)
    return bool(request.param)


def test_typeddict(pydantic_mode: bool) -> None:
    """TypedDicts validate without Pydantic."""
    assert validate.validate_json_data({"name": "x"}, Info) == {"name": "x"}


def test_typeddict_in_dict(pydantic_mode: bool) -> None:
    """TypedDicts nested in generics validate without Pydantic."""
    data = {"a": {"name": "x"}}
    assert validate.validate_json_data(data, dict[str, Info]) == data


def test_typeddict_rejects_non_dict(pydantic_mode: bool) -> None:
    """Non-dict data is rejected for TypedDicts."""
    with pytest.raises(TypeError):
        validate.validate_json_data(["x"], Info)


def test_literal(pydantic_mode: bool) -> None:
    """Typing constructs don't crash without Pydantic."""
    assert validate.validate_json_data("a", Literal["a", "b"]) == "a"  # type: ignore[arg-type]
