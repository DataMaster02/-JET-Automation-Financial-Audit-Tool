import traceback
import sys
import io
import contextlib
import pandas as pd
import numpy as np

def run_notebook_cell(code: str, env: dict) -> dict:
    """
    Executes a single cell of Python code in the provided environment.
    Captures stdout and returns the result (or error).
    """
    output_capture = io.StringIO()
    result = None
    error = None

    try:
        with contextlib.redirect_stdout(output_capture):
            # Attempt to run as an expression first to get the returned value
            try:
                result = eval(code, env)
            except SyntaxError:
                # If it's a statement (e.g. assignment), exec it
                exec(code, env)
                result = env.get("_result", None)
        env["_last_result"] = result
    except Exception as e:
        error = traceback.format_exc()

    is_df = isinstance(result, pd.DataFrame)
    is_series = isinstance(result, pd.Series)
    preview_df = result.head(50).to_frame() if is_series else result.head(50) if is_df else None
    return {
        "stdout": output_capture.getvalue(),
        "result": str(result) if result is not None else None,
        "is_dataframe": is_df,
        "is_series": is_series,
        "result_kind": "dataframe" if is_df else "series" if is_series else type(result).__name__ if result is not None else "none",
        "shape": list(result.shape) if is_df else [len(result), 1] if is_series else None,
        "columns": list(result.columns) if is_df else [result.name or "value"] if is_series else [],
        "html_table": preview_df.to_html(classes="gridtbl", index=False) if preview_df is not None else None,
        "error": error
    }

def create_safe_env(df: pd.DataFrame) -> dict:
    """
    Creates a restricted dictionary for exec/eval.
    """
    return {
        "__builtins__": {
            "print": print, "len": len, "range": range, "int": int, "float": float, 
            "str": str, "bool": bool, "list": list, "dict": dict, "set": set,
            "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
            "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError
        },
        "pd": pd,
        "np": np,
        "df": df.copy() # Provide a copy so original DataStore is not accidentally mangled directly without explicit save
    }
