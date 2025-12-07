"""Helper functions for the beam provider."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from beam import Image  # type: ignore[import-untyped]

    from anyenv.code_execution.parse_output import Language


def get_image(language: Language, deps: list[str]) -> Image:
    """Get an image for the given language and dependencies."""
    from beam import Image

    match language:
        case "python":
            return Image(python_version="python3.12", python_packages=deps)
        case "javascript" | "typescript":
            # Use a Node.js base image for JS/TS
            image = Image(base_image="node:20")
            if deps:
                deps_str = " ".join(deps)
                image.add_commands(f"npm install {deps_str}")
            return image
        case _:
            return Image(python_version="python3.12", python_packages=deps)
