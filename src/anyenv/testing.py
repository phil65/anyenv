"""Utilities for running async code in a synchronous context."""

from __future__ import annotations

import os
import types
from typing import Any

from anyenv.anypath import Path


def open_in_playground(
    file: types.ModuleType | str | os.PathLike[str],
    title: str = "Open in Pydantic Playground",
    dependencies: list[str] | None = None,
    open_browser: bool = True,
    **kwargs: Any,
) -> str:
    """Create a link to Pydantic playground with a pre-populated file.

    Args:
        file: The file to include in the playground. Can be:
               - A module
               - A file path
        title: The title of the link (not used in URL generation)
        dependencies: List of package dependencies to include as PEP 723 header
        open_browser: Whether to automatically open the link in a browser
        **kwargs: Additional keyword arguments to pass to the Pydantic playground

    Returns:
        A URL string pointing to the Pydantic playground
    """
    import inspect
    import json
    from urllib.parse import quote
    import webbrowser

    # Create file data based on the type of input
    match file:
        case types.ModuleType():
            content = inspect.getsource(file)
            filename = f"{file.__name__}.py"
        case str() | os.PathLike():
            file_path = Path(file)
            content = file_path.read_text("utf-8")
            filename = file_path.name
        case _:
            msg = f"Unsupported file type: {type(file)}"
            raise TypeError(msg)

    # Add PEP 723 header for dependencies if specified
    if dependencies:
        deps_str = ", ".join(f'"{dep}"' for dep in dependencies)
        pep723_header = f"# /// script\n# dependencies = [{deps_str}]\n# ///\n\n"
        content = pep723_header + content

    file_data = [{"name": filename, "content": content, "activeIndex": 1}]

    json_str = json.dumps(file_data)
    encoded = quote(json_str)

    url = f"https://pydantic.run/new?files={encoded}"

    if open_browser:
        webbrowser.open(url)

    return url


if __name__ == "__main__":
    open_in_playground(__file__, dependencies=["universal-pathlib"])
