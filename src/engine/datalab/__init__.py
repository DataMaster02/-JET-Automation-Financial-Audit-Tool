from .pandas_functions import register_pandas_formulas

def initialize_datalab_formulas():
    """
    Call this on application startup to register all available formulas.
    """
    register_pandas_formulas()
    # register_numpy_formulas()
    # register_excel_formulas()
