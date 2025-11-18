"""Output parsing utilities."""

from __future__ import annotations

from typing import Any, Literal


def parse_output(output: str) -> tuple[Any, dict[str, Any] | None]:
    """Parse result from sandbox output."""
    import anyenv

    try:
        lines = output.strip().split("\n")
        for line in lines:
            if line.startswith("__RESULT__"):
                result_json = line[len("__RESULT__") :].strip()
                result_data = anyenv.load_json(result_json, return_type=dict)

                if result_data.get("success", False):
                    return result_data.get("result"), None
                return None, {
                    "error": result_data.get("error", "Unknown error"),
                    "type": result_data.get("type", "Unknown"),
                }
    except anyenv.JsonLoadError as e:
        return None, {
            "error": f"Failed to parse result: {e}",
            "type": "JSONDecodeError",
        }
    except Exception as e:  # noqa: BLE001
        return None, {"error": str(e), "type": type(e).__name__}
    else:
        return None, {"error": "No execution result found", "type": "ParseError"}


def wrap_python_code(code: str) -> str:
    """Wrap Python code for execution."""
    return f"""
import asyncio
import json
import traceback
import inspect

# User code
{code}

# Execution wrapper
async def _execute_main():
    try:
        if "main" in globals() and callable(globals()["main"]):
            main_func = globals()["main"]
            if inspect.iscoroutinefunction(main_func):
                result = await main_func()
            else:
                result = main_func()
        else:
            result = globals().get("_result")
        return {{"result": result, "success": True}}
    except Exception as e:
        return {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}

# Run and output result
if __name__ == "__main__":
    try:
        execution_result = asyncio.run(_execute_main())
        print("__RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__RESULT__", json.dumps(error_result, default=str))
"""


def wrap_javascript_code(code: str) -> str:
    """Wrap JavaScript code for execution."""
    return f"""
// User code
{code}

// Execution wrapper
async function executeMain() {{
try {{
    let result;
    if (typeof main === 'function') {{
        result = await main();
    }} else if (typeof _result !== 'undefined') {{
        result = _result;
    }}
    return {{ result: result, success: true }};
}} catch (error) {{
    return {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
}}
}}

// Run and output result
(async () => {{
try {{
    const executionResult = await executeMain();
    console.log("__RESULT__", JSON.stringify(executionResult));
}} catch (error) {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log("__RESULT__", JSON.stringify(errorResult));
}}
}})();
"""


def wrap_typescript_code(code: str) -> str:
    """Wrap TypeScript code for execution."""
    return f"""
// User code
{code}

// Execution wrapper
async function executeMain(): Promise<{{
    result: any;
    success: boolean;
    error?: string;
    type?: string;
    traceback?: string;
}}> {{
    try {{
        let result: any;
        if (typeof main === 'function') {{
            result = await main();
        }} else if (typeof _result !== 'undefined') {{
            result = (global as any)._result;
        }}
        return {{ result: result, success: true }};
    }} catch (error: any) {{
        return {{
            success: false,
            error: error.message,
            type: error.name,
            traceback: error.stack
        }};
    }}
}}

// Run and output result
executeMain().then(result => {{
    console.log('__RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__RESULT__', JSON.stringify(errorResult));
}});
"""


Language = Literal["python", "javascript", "typescript"]


def wrap_code(code: str, language: Language) -> str:
    """Wrap user code for Modal execution with result capture."""
    match language:
        case "python":
            return wrap_python_code(code)
        case "javascript":
            return wrap_javascript_code(code)
        case "typescript":
            return wrap_typescript_code(code)
        case _:
            return wrap_python_code(code)


def get_script_path(language: Language) -> str:
    """Get script path based on language."""
    match language:
        case "python":
            return "/tmp/execution_script.py"
        case "javascript":
            return "/tmp/execution_script.js"
        case "typescript":
            return "/tmp/execution_script.ts"
        case _:
            return "/tmp/execution_script.py"


def wrap_command(command: str) -> str:
    """Wrap command to run in login shell for proper PATH setup."""
    # Escape single quotes in the command
    escaped_command = command.replace("'", "'\"'\"'")
    return f"bash -l -c '{escaped_command}'"
