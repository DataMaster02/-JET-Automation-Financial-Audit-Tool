# ================================================================
# engine/datalab/registry.py
# Formula metadata and registration
# ================================================================

import logging
from typing import Dict, Any, Callable

logger = logging.getLogger("jet.datalab.registry")

# Global registry of all formulas
_FORMULA_REGISTRY: Dict[str, Dict[str, Any]] = {}

def register_formula(
    id: str,
    name: str,
    category: str,
    description: str,
    engine: str, # 'pandas', 'numpy', 'python', 'custom'
    parameters: list,
    python_equivalent: str,
    excel_equivalent: str,
    example: dict,
    execute_fn: Callable
):
    """
    Registers a new formula for the DataLab Formula Builder.
    """
    _FORMULA_REGISTRY[id] = {
        "id": id,
        "name": name,
        "category": category,
        "description": description,
        "engine": engine,
        "parameters": parameters,
        "python_equivalent": python_equivalent,
        "excel_equivalent": excel_equivalent,
        "example": example,
        "execute_fn": execute_fn
    }
    logger.debug(f"Registered formula: {id} ({name})")

def get_all_formulas() -> list:
    """Returns a list of all registered formulas (excluding the execute function for serialization)."""
    formulas = []
    for f in _FORMULA_REGISTRY.values():
        formula_meta = f.copy()
        formula_meta.pop("execute_fn", None)
        formulas.append(formula_meta)
    return formulas

def get_formula(id: str) -> dict:
    """Returns the full formula definition including the execute function."""
    return _FORMULA_REGISTRY.get(id)
