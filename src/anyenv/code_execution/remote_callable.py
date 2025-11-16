"""Remote callable wrapper utilities."""

from __future__ import annotations

import inspect
import json
import shlex
import sys
import textwrap
from typing import TYPE_CHECKING, Any, ParamSpec, get_type_hints

from anyenv.code_execution.docker_provider.provider import DockerExecutionEnvironment


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from anyenv.code_execution.base import ExecutionEnvironment

CallableP = ParamSpec("CallableP")  # For the callable's parameters
EnvP = ParamSpec("EnvP")  # For the environment's parameters


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

# Serialize result - handle Pydantic models specially
if hasattr(result, 'model_dump'):
    # Pydantic model - serialize to dict first
    result_data = result.model_dump()
else:
    result_data = result

print(json.dumps(result_data, default=str))
"""

MAIN_MODULE_CODE = """
import json
import sys

{imports}

{source_code}

# Deserialize arguments
args = json.loads(sys.argv[1])
kwargs = json.loads(sys.argv[2])

# Execute function
result = {func_name}(*args, **kwargs)

# Serialize result - handle Pydantic models specially
if hasattr(result, 'model_dump'):
    # Pydantic model - serialize to dict first
    result_data = result.model_dump()
else:
    result_data = result

print(json.dumps(result_data, default=str))
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


def create_remote_callable[R, **CallableP, **EnvP](
    callable_obj: Callable[CallableP, R] | str,
    env_class: Callable[EnvP, ExecutionEnvironment],
    *args: EnvP.args,
    **kwargs: EnvP.kwargs,
) -> Callable[CallableP, Awaitable[R]]:
    """Create a remote-executing version of a callable.

    Analyzes the callable to infer dependencies, then returns a wrapped
    version that executes in an isolated environment.

    Args:
        callable_obj: Function or import path to wrap
        env_class: ExecutionEnvironment class to use
        *args: Constructor arguments for the environment
        **kwargs: Constructor keyword arguments for the environment

    Returns:
        Wrapped callable that executes remotely
    """
    # Get import path and capture return type
    return_type = None
    if isinstance(callable_obj, str):
        import_path = callable_obj
        is_main_module = False
        source_code = None
        func_name = import_path.split(".")[-1]
    else:
        # Capture return type annotation for type-safe deserialization
        try:
            # Use get_type_hints to resolve string annotations to actual types
            type_hints = get_type_hints(callable_obj)
            return_type = type_hints.get("return")
        except (NameError, AttributeError):
            # Fallback to raw annotations if resolution fails
            return_type = (
                callable_obj.__annotations__.get("return")
                if hasattr(callable_obj, "__annotations__")
                else None
            )

        module = callable_obj.__module__
        if hasattr(callable_obj, "__qualname__"):
            import_path = f"{module}.{callable_obj.__qualname__}"
        else:
            import_path = f"{module}.{callable_obj.__class__.__qualname__}"

        # Handle __main__ module case
        is_main_module = module == "__main__"
        if is_main_module:
            # Get source and dedent it
            source_code = textwrap.dedent(inspect.getsource(callable_obj))
            func_name = callable_obj.__name__

            # Extract imports and class definitions from the main module
            main_module = sys.modules["__main__"]
            imports = []
            class_defs = []

            for obj in vars(main_module).values():
                if (
                    isinstance(obj, type)
                    and hasattr(obj, "__module__")
                    and obj.__module__ == "__main__"
                ):
                    # This is a class defined in main
                    class_source = textwrap.dedent(inspect.getsource(obj))
                    class_defs.append(class_source)
                    # Add imports for the class (basic detection)
                    if hasattr(obj, "__bases__"):
                        for base in obj.__bases__:
                            if base.__module__ != "builtins":
                                imports.append(  # noqa: PERF401
                                    f"from {base.__module__} import {base.__name__}"
                                )

            # Combine imports and class definitions
            all_imports = "\n".join(set(imports))  # Remove duplicates
            all_classes = "\n".join(class_defs)
            imports_and_classes = f"{all_imports}\n\n{all_classes}".strip()
        else:
            source_code = None
            func_name = import_path.split(".")[-1]
            imports_and_classes = ""

    # Infer package dependencies
    dependencies = infer_package_dependencies(import_path)
    # Filter out invalid packages like __main__
    dependencies = [dep for dep in dependencies if not dep.startswith("__")]

    # Auto-detect Pydantic dependency if BaseModel is used in __main__ module
    if (
        is_main_module
        and imports_and_classes
        and "BaseModel" in imports_and_classes
        and "pydantic" not in dependencies
    ):
        dependencies.append("pydantic")

    async def remote_wrapper(*func_args: Any, **func_kwargs: Any) -> R:
        """Wrapper that executes the callable remotely."""
        import anyenv

        # Create execution code based on whether it's from __main__ or not
        if is_main_module:
            code = MAIN_MODULE_CODE.format(
                imports=imports_and_classes, source_code=source_code, func_name=func_name
            )
        else:
            module_path = ".".join(import_path.split(".")[:-1])
            code = CODE.format(module_path=module_path, func_name=func_name)

        # Set up environment and execute
        # Merge dependencies with user kwargs, user kwargs take precedence
        env_kwargs = {"dependencies": dependencies, **kwargs}

        async with env_class(*args, **env_kwargs) as env:  # type: ignore
            args_json = json.dumps(func_args, default=str)
            kwargs_json = json.dumps(func_kwargs, default=str)
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

            # Parse result with type validation if return type is available
            if return_type is not None:
                try:
                    result_str = result.stdout or "null"
                    return anyenv.load_json(result_str, return_type=return_type)
                except TypeError:
                    # Fallback: if type validation fails, try reconstructing from dict
                    data = anyenv.load_json(result.stdout or "null")
                    if hasattr(return_type, "model_validate") and isinstance(data, dict):
                        return return_type.model_validate(data)
                    return data
            return anyenv.load_json(result.stdout or "null")

    return remote_wrapper


if __name__ == "__main__":
    import asyncio

    from pydantic import BaseModel

    from anyenv.code_execution.docker_provider.provider import DockerExecutionEnvironment

    class Person(BaseModel):
        """A person with name, age, and optional email."""

        name: str
        age: int
        email: str | None = None

    def create_person(name: str, age: int, email: str | None = None) -> Person:
        """Create and return a Person BaseModel."""
        return Person(name=name, age=age, email=email)

    async def main() -> None:
        """Run the main program."""
        print("\n=== Testing Pydantic BaseModel round-trip ===")
        remote_create_person = create_remote_callable(
            create_person,
            DockerExecutionEnvironment,
            timeout=60.0,
        )
        person = await remote_create_person("Alice", 30, "alice@example.com")
        print(f"Result: {person!r}")
        print(f"Type: {type(person)}")
        print(f"Name: {person.name}")
        print(f"Age: {person.age}")
        print(f"Email: {person.email}")
        print(f"Is Person instance: {isinstance(person, Person)}")
        print("✅ Completed Pydantic BaseModel round-trip with full type safety!")

    asyncio.run(main())
