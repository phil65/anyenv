"""Local execution environment that runs code in the same process."""

from __future__ import annotations

import inspect
import time

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


class LocalExecutionEnvironment(ExecutionEnvironment):
    """Executes code in the same process (current behavior)."""

    async def __aenter__(self) -> ExecutionEnvironment:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code directly in current process."""
        start_time = time.time()

        try:
            namespace = {"__builtins__": __builtins__}
            exec(code, namespace)

            # Try to get result from main() function
            if "main" in namespace and callable(namespace["main"]):
                main_func = namespace["main"]
                if inspect.iscoroutinefunction(main_func):
                    result = await main_func()
                else:
                    result = main_func()
            else:
                result = namespace.get("_result")

            duration = time.time() - start_time
            return ExecutionResult(result=result, duration=duration, success=True)

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )
