# ================================================================
# engine/datalab/formula_engine.py
# Executes a workflow of DataLab nodes
# ================================================================

import pandas as pd
from typing import List, Dict, Any
from .registry import get_formula

def execute_workflow(df: pd.DataFrame, workflow: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Executes a list of formula nodes sequentially on a DataFrame.
    """
    current_df = df.copy()

    for node in workflow:
        formula_id = node.get("formula_id")
        params = node.get("params", {})
        
        formula_def = get_formula(formula_id)
        if not formula_def:
            raise ValueError(f"Formula '{formula_id}' not found in registry.")
            
        execute_fn = formula_def.get("execute_fn")
        if not execute_fn:
            raise ValueError(f"Execution function for '{formula_id}' not found.")
            
        # The execution function is responsible for applying the logic
        # It receives the current dataframe and its parameters
        current_df = execute_fn(current_df, **params)

    return current_df
