# ================================================================
# engine/datalab/pandas_functions.py
# Definitions for Pandas-based formulas
# ================================================================

import pandas as pd
import numpy as np
from typing import Any
from .registry import register_formula

# --- Execution Functions ---

def _execute_fillna(df: pd.DataFrame, column: str, value: Any, new_column: str) -> pd.DataFrame:
    df[new_column] = df[column].fillna(value)
    return df

def _execute_upper(df: pd.DataFrame, column: str, new_column: str) -> pd.DataFrame:
    df[new_column] = df[column].astype(str).str.upper()
    return df

def _execute_sum(df: pd.DataFrame, columns: list, new_column: str) -> pd.DataFrame:
    df[new_column] = df[columns].sum(axis=1, numeric_only=True)
    return df

# --- Formula Registrations ---

def register_pandas_formulas():
    register_formula(
        id="pd_fillna",
        name="Fill Missing Values",
        category="Data Cleaning",
        description="Replaces missing (NaN) values in a column with a specified static value.",
        engine="pandas",
        parameters=[
            {"id": "column", "name": "Column to Fill", "type": "column"},
            {"id": "value", "name": "Value to Fill With", "type": "text", "default": "0"},
            {"id": "new_column", "name": "New Column Name", "type": "text", "default": "filled_column"}
        ],
        python_equivalent="df['new_column'] = df['column'].fillna(value)",
        excel_equivalent="=IF(ISBLANK(A1), value, A1)",
        example={
            "before": pd.DataFrame({'A': [1, 2, np.nan, 4]}),
            "after": pd.DataFrame({'A': [1, 2, np.nan, 4], 'A_filled': [1, 2, 0, 4]})
        },
        execute_fn=_execute_fillna
    )

    register_formula(
        id="pd_upper",
        name="Convert to Uppercase",
        category="String Functions",
        description="Converts all text in a column to uppercase.",
        engine="pandas",
        parameters=[
            {"id": "column", "name": "Text Column", "type": "column"},
            {"id": "new_column", "name": "New Column Name", "type": "text", "default": "upper_column"}
        ],
        python_equivalent="df['new_column'] = df['column'].str.upper()",
        excel_equivalent="=UPPER(A1)",
        example={
            "before": pd.DataFrame({'text': ['hello', 'World']}),
            "after": pd.DataFrame({'text': ['hello', 'World'], 'text_upper': ['HELLO', 'WORLD']})
        },
        execute_fn=_execute_upper
    )
    
    register_formula(
        id="pd_sum",
        name="Row-wise Sum",
        category="Math Functions",
        description="Calculates the sum of multiple numeric columns for each row.",
        engine="pandas",
        parameters=[
            {"id": "columns", "name": "Columns to Sum", "type": "column_multi"},
            {"id": "new_column", "name": "New Column Name", "type": "text", "default": "total"}
        ],
        python_equivalent="df['total'] = df[['col1', 'col2']].sum(axis=1)",
        excel_equivalent="=SUM(A1:B1)",
        example={
            "before": pd.DataFrame({'A': [1, 2, 3], 'B': [10, 20, 30]}),
            "after": pd.DataFrame({'A': [1, 2, 3], 'B': [10, 20, 30], 'total': [11, 22, 33]})
        },
        execute_fn=_execute_sum
    )
