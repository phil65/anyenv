"""Remote callable wrapper utilities."""

from __future__ import annotations

import inspect
import json
import shlex
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable

    from anyenv.code_execution.base import ExecutionEnvironment

# Common module->package mappings for edge cases
MODULE_TO_PACKAGE = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "requests": "requests",
    "numpy": "numpy",
    "pandas": "pandas",
}

CODE = """
import json
import sys
from {module_path} import {func_name}

# Deserialize arguments
args = json.loads(sys.argv[1])
kwargs = json.loads(sys.argv[2])

# Execute function
result = {func_name}(*args, **kwargs)

# Serialize result
print(json.dumps(result, default=str))
"""

MAIN_MODULE_CODE = """
import json
import sys

{source_code}

# Deserialize arguments
args = json.loads(sys.argv[1])
kwargs = json.loads(sys.argv[2])

# Execute function
result = {func_name}(*args, **kwargs)

# Serialize result
print(json.dumps(result, default=str))
"""


def infer_package_dependencies(import_path: str) -> list[str]:
    """Infer package dependencies from import path.

    Args:
        import_path: Import path like 'requests.get' or 'pandas.DataFrame'

    Returns:
        List of package names to install
    """
    if not import_path:
        return []

    # Get the root module name
    root_module = import_path.split(".")[0]
    packages = []

    try:
        import importlib.metadata

        # Try to find which package provides this module
        pkg_to_modules = importlib.metadata.packages_distributions()
        for pkg, modules in pkg_to_modules.items():
            if root_module in modules:
                packages.append(pkg)
                break
    except Exception:  # noqa: BLE001
        pass

    # If not found via metadata, use heuristic + mapping
    if not packages:
        package = MODULE_TO_PACKAGE.get(root_module, root_module)
        packages.append(package)

    return packages


def create_remote_callable(
    callable_obj: Callable[..., Any] | str,
    env_class: type[ExecutionEnvironment],
    **env_kwargs: Any,
) -> Callable[..., Any]:
    """Create a remote-executing version of a callable.

    Analyzes the callable to infer dependencies, then returns a wrapped
    version that executes in an isolated environment.

    Args:
        callable_obj: Function or import path to wrap
        env_class: ExecutionEnvironment class to use
        **env_kwargs: Additional environment setup arguments

    Returns:
        Wrapped callable that executes remotely
    """
    # Get import path and infer dependencies
    if isinstance(callable_obj, str):
        import_path = callable_obj
        is_main_module = False
        source_code = None
        func_name = import_path.split(".")[-1]
    else:
        module = callable_obj.__module__
        if hasattr(callable_obj, "__qualname__"):
            import_path = f"{module}.{callable_obj.__qualname__}"
        else:
            import_path = f"{module}.{callable_obj.__class__.__qualname__}"

        # Handle __main__ module case
        is_main_module = module == "__main__"
        if is_main_module:
            source_code = inspect.getsource(callable_obj)
            func_name = callable_obj.__name__
        else:
            source_code = None
            func_name = import_path.split(".")[-1]

    # Infer package dependencies
    dependencies = infer_package_dependencies(import_path)

    async def remote_wrapper(*args: Any, **kwargs: Any) -> Any:
        """Wrapper that executes the callable remotely."""
        import anyenv

        # Create execution code based on whether it's from __main__ or not
        if is_main_module:
            code = MAIN_MODULE_CODE.format(source_code=source_code, func_name=func_name)
        else:
            module_path = ".".join(import_path.split(".")[:-1])
            code = CODE.format(module_path=module_path, func_name=func_name)

        # Set up environment and execute
        async with env_class(dependencies=dependencies, **env_kwargs) as env:
            args_json = json.dumps(args, default=str)
            kwargs_json = json.dumps(kwargs, default=str)

            # Execute with arguments passed as command line args
            # Use shlex.quote to properly escape the arguments
            escaped_code = shlex.quote(code)
            escaped_args = shlex.quote(args_json)
            escaped_kwargs = shlex.quote(kwargs_json)

            result = await env.execute_command(
                f"python -c {escaped_code} {escaped_args} {escaped_kwargs}"
            )

            if not result.success:
                msg = f"Remote execution failed: {result.error}"
                raise RuntimeError(msg)
            # Parse result
            return anyenv.load_json(result.stdout or "null")

    return remote_wrapper


def greet(name):
    """Return a greeting message."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    import asyncio

    from anyenv.code_execution.local_provider import LocalExecutionEnvironment

    async def main():
        """Run the main program."""
        result = create_remote_callable(greet, LocalExecutionEnvironment)
        output = await result("World")
        print(output)

    asyncio.run(main())
