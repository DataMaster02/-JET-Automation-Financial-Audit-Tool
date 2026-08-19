import pandas as pd
import numpy as np
import math
import re

NUMERIC_ABS_LIMIT = 1e75


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        raise ValueError(f"Column not found: {col}")
    return _coerce_numeric(df[col])


def _coerce_numeric(values) -> pd.Series:
    s = values if isinstance(values, pd.Series) else pd.Series(values)
    if pd.api.types.is_numeric_dtype(s):
        return _finite_series(pd.to_numeric(s, errors="coerce"))

    text = s.astype("string").fillna("").str.strip()
    text = text.str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False)
    neg = text.str.match(r"^\(.*\)$", na=False)
    text = text.str.replace(r"^\((.*)\)$", r"\1", regex=True)
    is_percent = text.str.endswith("%", na=False)
    text = text.str.replace("%", "", regex=False)
    text = text.str.replace(r"[^0-9,\.\-eE+]", "", regex=True)

    comma = text.str.rfind(",")
    dot = text.str.rfind(".")
    both = comma.ge(0) & dot.ge(0)
    comma_decimal = both & comma.gt(dot)
    dot_decimal = both & dot.gt(comma)
    only_comma = comma.ge(0) & dot.lt(0)

    normalized = text.copy()
    normalized.loc[comma_decimal] = normalized.loc[comma_decimal].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    normalized.loc[dot_decimal] = normalized.loc[dot_decimal].str.replace(",", "", regex=False)
    normalized.loc[only_comma] = normalized.loc[only_comma].str.replace(",", ".", regex=False)
    out = pd.to_numeric(normalized, errors="coerce")
    out.loc[neg] = -out.loc[neg]
    out.loc[is_percent] = out.loc[is_percent] / 100
    return _finite_series(out)


def _finite_series(s: pd.Series) -> pd.Series:
    out = s.replace([np.inf, -np.inf], np.nan)
    return out.mask(out.abs() > NUMERIC_ABS_LIMIT)


def _finite_frame(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(_coerce_numeric).replace([np.inf, -np.inf], np.nan)


def _safe_float(value, default=0.0):
    try:
        if pd.isna(value) or not np.isfinite(value):
            return default
        return float(value)
    except Exception:
        return default


def _safe_std(s: pd.Series, ddof: int = 0):
    values = _finite_series(s).dropna().astype(float)
    if len(values) <= ddof:
        return np.nan
    with np.errstate(all="ignore"):
        return values.std(ddof=ddof)


def _safe_var(s: pd.Series, ddof: int = 0):
    values = _finite_series(s).dropna().astype(float)
    if len(values) <= ddof:
        return np.nan
    with np.errstate(all="ignore"):
        return values.var(ddof=ddof)


def _safe_skew(s: pd.Series):
    values = _finite_series(s).dropna().astype(float)
    if len(values) < 3:
        return 0.0
    centered = values - values.mean()
    std = centered.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return 0.0
    with np.errstate(all="ignore"):
        z = centered / std
        return _safe_float(np.mean(z ** 3))


def _safe_kurt(s: pd.Series):
    values = _finite_series(s).dropna().astype(float)
    if len(values) < 4:
        return 0.0
    centered = values - values.mean()
    std = centered.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return 0.0
    with np.errstate(all="ignore"):
        z = centered / std
        return _safe_float(np.mean(z ** 4) - 3.0)


def _row_stat(frame: pd.DataFrame, func, default=np.nan) -> pd.Series:
    return frame.apply(lambda r: _safe_float(func(r), default), axis=1)


def _safe_identifier(name: str) -> str:
    ident = re.sub(r"\W+", "_", str(name), flags=re.UNICODE).strip("_")
    if not ident or ident[0].isdigit():
        ident = f"col_{ident}"
    return ident


def _formula_env(df: pd.DataFrame, numeric_mode: bool = True) -> dict:
    def col(name):
        if name not in df.columns:
            raise ValueError(f"Column not found: {name}")
        return df[name]

    def num(value):
        if isinstance(value, str) and value in df.columns:
            return _num(df, value)
        return _coerce_numeric(value)

    def txt(value):
        if isinstance(value, str) and value in df.columns:
            return df[value].astype("string").fillna("")
        if isinstance(value, pd.Series):
            return value.astype("string").fillna("")
        return pd.Series([str(value)] * len(df), index=df.index, dtype="string")

    def frame(*values, numeric=True):
        if not values:
            return pd.DataFrame(index=df.index)
        data = {}
        for idx, value in enumerate(values):
            if isinstance(value, str) and value in df.columns:
                s = _num(df, value) if numeric else df[value]
            elif isinstance(value, pd.Series):
                s = _coerce_numeric(value) if numeric else value
            else:
                s = pd.Series([value] * len(df), index=df.index)
                if numeric:
                    s = _coerce_numeric(s)
            data[str(idx)] = s.reindex(df.index)
        return pd.DataFrame(data, index=df.index)

    def row_stat(func, *values, default=np.nan):
        return _row_stat(frame(*values), func, default=default)

    def iferror(value, fallback=""):
        if isinstance(value, pd.Series):
            return value.replace([np.inf, -np.inf], np.nan).fillna(fallback)
        return fallback if pd.isna(value) else value

    env = {
        "df": df,
        "np": np,
        "pd": pd,
        "COL": col,
        "NUM": num,
        "TXT": txt,
        "ABS": lambda x: num(x).abs(),
        "SUM": lambda *xs: frame(*xs).sum(axis=1),
        "PRODUCT": lambda *xs: frame(*xs).product(axis=1),
        "AVERAGE": lambda *xs: frame(*xs).mean(axis=1),
        "MEAN": lambda *xs: frame(*xs).mean(axis=1),
        "MEDIAN": lambda *xs: frame(*xs).median(axis=1),
        "MIN": lambda *xs: frame(*xs).min(axis=1),
        "MAX": lambda *xs: frame(*xs).max(axis=1),
        "COUNT": lambda *xs: frame(*xs).notna().sum(axis=1),
        "COUNTA": lambda *xs: frame(*xs, numeric=False).notna().sum(axis=1),
        "ROUND": lambda x, decimals=0: num(x).round(int(decimals)),
        "ROUNDUP": lambda x, decimals=0: np.ceil(num(x) * (10 ** int(decimals))) / (10 ** int(decimals)),
        "ROUNDDOWN": lambda x, decimals=0: np.floor(num(x) * (10 ** int(decimals))) / (10 ** int(decimals)),
        "INT": lambda x: np.floor(num(x)),
        "TRUNC": lambda x, decimals=0: np.trunc(num(x) * (10 ** int(decimals))) / (10 ** int(decimals)),
        "CEILING": lambda x, significance=1: np.ceil(num(x) / float(significance)) * float(significance),
        "FLOOR": lambda x, significance=1: np.floor(num(x) / float(significance)) * float(significance),
        "MOD": lambda x, y: num(x) % num(y),
        "POWER": lambda x, y: _finite_series(pd.Series(np.power(num(x), num(y)), index=df.index)),
        "SQRT": lambda x: np.sqrt(num(x).where(num(x) >= 0)),
        "EXP": lambda x: _finite_series(pd.Series(np.exp(num(x)), index=df.index)),
        "LN": lambda x: np.log(num(x).where(num(x) > 0)),
        "LOG": lambda x, base=10: np.log(num(x).where(num(x) > 0)) / np.log(float(base)),
        "LOG10": lambda x: np.log10(num(x).where(num(x) > 0)),
        "SIGN": lambda x: np.sign(num(x)),
        "PI": lambda: math.pi,
        "RADIANS": lambda x: np.radians(num(x)),
        "DEGREES": lambda x: np.degrees(num(x)),
        "SIN": lambda x: np.sin(num(x)),
        "COS": lambda x: np.cos(num(x)),
        "TAN": lambda x: np.tan(num(x)),
        "ASIN": lambda x: np.arcsin(num(x).where(num(x).between(-1, 1))),
        "ACOS": lambda x: np.arccos(num(x).where(num(x).between(-1, 1))),
        "ATAN": lambda x: np.arctan(num(x)),
        "ATAN2": lambda x, y: np.arctan2(num(x), num(y)),
        "SINH": lambda x: np.sinh(num(x)),
        "COSH": lambda x: np.cosh(num(x)),
        "TANH": lambda x: np.tanh(num(x)),
        "ASINH": lambda x: np.arcsinh(num(x)),
        "ACOSH": lambda x: np.arccosh(num(x).where(num(x) >= 1)),
        "ATANH": lambda x: np.arctanh(num(x).where(num(x).between(-1, 1, inclusive="neither"))),
        "COT": lambda x: _finite_series(1 / np.tan(num(x))),
        "SEC": lambda x: _finite_series(1 / np.cos(num(x))),
        "CSC": lambda x: _finite_series(1 / np.sin(num(x))),
        "EVEN": lambda x: np.ceil(num(x) / 2) * 2,
        "ODD": lambda x: pd.Series(np.where((np.ceil(num(x)) % 2) == 0, np.ceil(num(x)) + 1, np.ceil(num(x))), index=df.index),
        "PERCENTILE_INC": lambda q, *xs: frame(*xs).quantile(float(q), axis=1),
        "QUARTILE_INC": lambda quart, *xs: frame(*xs).quantile(float(quart) / 4, axis=1),
        "STDEV_P": lambda *xs: row_stat(lambda r: _safe_std(r, ddof=0), *xs),
        "STDEV_S": lambda *xs: row_stat(lambda r: _safe_std(r, ddof=1), *xs),
        "VAR_P": lambda *xs: row_stat(lambda r: _safe_var(r, ddof=0), *xs),
        "VAR_S": lambda *xs: row_stat(lambda r: _safe_var(r, ddof=1), *xs),
        "SKEW": lambda *xs: row_stat(_safe_skew, *xs, default=0.0),
        "KURT": lambda *xs: row_stat(_safe_kurt, *xs, default=0.0),
        "IF": lambda condition, true_value, false_value="": np.where(condition, true_value, false_value),
        "IFERROR": iferror,
        "AND": lambda *xs: frame(*xs, numeric=False).apply(lambda r: all(_bool_series(r)), axis=1),
        "OR": lambda *xs: frame(*xs, numeric=False).apply(lambda r: any(_bool_series(r)), axis=1),
        "NOT": lambda x: ~_bool_series(x if isinstance(x, pd.Series) else col(x)),
        "LEN": lambda x: txt(x).str.len(),
        "UPPER": lambda x: txt(x).str.upper(),
        "LOWER": lambda x: txt(x).str.lower(),
        "TRIM": lambda x: txt(x).str.strip(),
        "CONCAT": lambda *xs, sep="": frame(*xs, numeric=False).astype("string").fillna("").agg(str(sep).join, axis=1),
        "TEXTJOIN": lambda sep, *xs: frame(*xs, numeric=False).astype("string").fillna("").agg(str(sep).join, axis=1),
        "TODAY": lambda: pd.Timestamp.today().normalize(),
        "NOW": lambda: pd.Timestamp.now(),
        "YEAR": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.year,
        "MONTH": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.month,
        "DAY": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.day,
        "HOUR": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.hour,
        "MINUTE": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.minute,
        "SECOND": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.second,
        "WEEKDAY": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.weekday + 1,
        "WEEKNUM": lambda x: pd.to_datetime(col(x) if isinstance(x, str) and x in df.columns else x, errors="coerce").dt.isocalendar().week.astype("Int64"),
        "DAYS": lambda end, start: (pd.to_datetime(end, errors="coerce") - pd.to_datetime(start, errors="coerce")).dt.days,
    }
    for c in df.columns:
        value = _coerce_numeric(df[c]) if numeric_mode else df[c]
        if c not in env:
            env[c] = value
        ident = _safe_identifier(c)
        if ident not in env:
            env[ident] = value
    return env


def _int_arg(args: dict, key: str, default: int) -> int:
    try:
        return int(float(args.get(key, default)))
    except Exception:
        return default


def _float_arg(args: dict, key: str, default: float) -> float:
    try:
        return float(args.get(key, default))
    except Exception:
        return default


def _bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.fillna(False)
    text = s.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "evet", "dogru", "doğru"})


def _row_factorial(s: pd.Series) -> pd.Series:
    def calc(v):
        if pd.isna(v) or v < 0:
            return np.nan
        try:
            return math.factorial(int(v))
        except Exception:
            return np.nan
    return s.apply(calc)


def _selected_frame(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    if not cols:
        raise ValueError("Select at least one column")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Column not found: {', '.join(missing)}")
    return df[cols]


def _numeric_profile(s: pd.Series) -> dict:
    s = _finite_series(s).dropna()
    if s.empty:
        return {}
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return {
        "mean": _safe_float(s.mean()),
        "std": _safe_float(_safe_std(s, ddof=0)),
        "percentile_5": _safe_float(s.quantile(0.05)),
        "percentile_25": _safe_float(q1),
        "percentile_50": _safe_float(s.quantile(0.50)),
        "percentile_75": _safe_float(q3),
        "percentile_95": _safe_float(s.quantile(0.95)),
        "min": _safe_float(s.min()),
        "max": _safe_float(s.max()),
        "range": _safe_float(s.max() - s.min()),
        "q1": _safe_float(q1),
        "q3": _safe_float(q3),
        "iqr": _safe_float(iqr),
        "variance": _safe_float(_safe_var(s, ddof=0)),
        "median": _safe_float(s.median()),
        "skewness": _safe_float(_safe_skew(s)),
        "kurtosis": _safe_float(_safe_kurt(s)),
        "outlier_count": int(((s < lower) | (s > upper)).sum()),
        "histogram": np.histogram(s, bins=min(20, max(5, int(np.sqrt(len(s))))))[0].tolist(),
    }


def run_module_preview(df: pd.DataFrame, config: dict):
    preview_df = df.head(10).copy()
    try:
        res_df = apply_module(preview_df, config)
        return {"ok": True, "preview": res_df.to_dict(orient="records"), "columns": list(res_df.columns)}
    except Exception as e:
        return {"error": str(e)}


def run_module_execute(df: pd.DataFrame, config: dict):
    try:
        res_df = apply_module(df, config)
        return {"ok": True, "df": res_df}
    except Exception as e:
        return {"error": str(e)}


def apply_module(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    # Backward-compatible wrapper for the older DataLab module calls.
    category = config.get("category")
    operation = config.get("operation")
    if category == "groupby":
        return _apply_groupby(df, {
            "group_cols": config.get("group_cols", []),
            "aggs": [{
                "column": config.get("val_col"),
                "agg": config.get("agg_func", "sum"),
                "name": config.get("newCol", "group_value"),
            }],
        })
    if category == "custom":
        return apply_column_tools(df, {
            "op": "formula",
            "new_col": config.get("newCol", "custom_result"),
            "expr": config.get("code", ""),
        })
    return apply_column_tools(df, {
        "op": "function",
        "fn": _legacy_function_id(category, operation),
        "cols": config.get("cols", []),
        "new_col": config.get("newCol", f"{operation}_result"),
        "args": config,
    })


def _legacy_function_id(category: str, operation: str) -> str:
    mapping = {
        ("text", "concat"): "excel_concat",
        ("text", "upper"): "excel_upper",
        ("text", "lower"): "excel_lower",
        ("text", "trim"): "excel_trim",
        ("text", "left"): "excel_left",
        ("text", "right"): "excel_right",
        ("text", "replace"): "pd_replace",
        ("numeric", "round"): "excel_round",
        ("numeric", "abs"): "excel_abs",
        ("stats", "mean"): "np_mean",
        ("stats", "std"): "np_std",
        ("stats", "percentile"): "np_percentile",
        ("stats", "zscore"): "np_zscore",
        ("stats", "outlier"): "np_zscore",
    }
    if category == "numeric" and operation == "math":
        return "excel_sum"
    return mapping.get((category, operation), "excel_sum")


def build_profile(df: pd.DataFrame) -> dict:
    rows = []
    total_rows = len(df) or 1
    for col in df.columns:
        s_raw = df[col]
        s_txt = s_raw.astype("string").fillna("").replace({"nan": "", "None": ""})
        s_num = _coerce_numeric(s_raw)
        non_empty = s_txt.ne("")
        numeric_non_null = s_num.dropna()
        vc = s_txt[non_empty].value_counts()
        probs = vc / vc.sum() if vc.sum() else pd.Series(dtype=float)
        row = {
            "column": col,
            "missing_pct": round((int((~non_empty).sum()) / total_rows) * 100, 2),
            "distinct": int(s_txt[non_empty].nunique()),
            "unique": int((vc == 1).sum()) if not vc.empty else 0,
            "top_values": vc.head(3).to_dict(),
            "bottom_values": vc.tail(3).to_dict(),
            "memory_usage": int(s_raw.memory_usage(deep=True)),
            "null_count": int((~non_empty).sum()),
            "duplicate_count": int(len(s_txt[non_empty]) - int((vc == 1).sum())) if not vc.empty else 0,
            "entropy": float(-(probs * np.log2(probs)).sum()) if not probs.empty else 0.0,
        }
        if not numeric_non_null.empty:
            prof = _numeric_profile(numeric_non_null)
            mode_series = numeric_non_null.mode(dropna=True)
            row.update({
                "outlier_count": prof.get("outlier_count", 0),
                "negative_count": int((numeric_non_null < 0).sum()),
                "zero_count": int((numeric_non_null == 0).sum()),
                "skewness": prof.get("skewness", 0.0),
                "kurtosis": prof.get("kurtosis", 0.0),
                "variance": prof.get("variance", 0.0),
                "std": prof.get("std", 0.0),
                "median": prof.get("median", 0.0),
                "mode": float(mode_series.iloc[0]) if not mode_series.empty else None,
                "min": prof.get("min", 0.0),
                "max": prof.get("max", 0.0),
                "range": prof.get("range", 0.0),
                "q1": prof.get("q1", 0.0),
                "q3": prof.get("q3", 0.0),
                "iqr": prof.get("iqr", 0.0),
                "mean": prof.get("mean", 0.0),
                "percentile_5": prof.get("percentile_5"),
                "percentile_25": prof.get("percentile_25"),
                "percentile_50": prof.get("percentile_50"),
                "percentile_75": prof.get("percentile_75"),
                "percentile_95": prof.get("percentile_95"),
                "histogram": prof.get("histogram", []),
            })
        rows.append(row)
    return {"columns": rows}


def apply_column_tools(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    op = config.get("op")
    cols = config.get("cols", [])
    new_col = (config.get("new_col") or "").strip()
    if op == "filter":
        return _apply_filter(df, config)
    if op == "ready_filter":
        return _apply_ready_filter(df, config)
    if op == "ready_filter_chain":
        return _apply_ready_filter_chain(df, config)
    if op == "function":
        return _apply_named_function(df, config)
    if op == "groupby":
        return _apply_groupby(df, config)
    if op == "drop":
        return df[[c for c in df.columns if c not in cols]].copy()
    if op == "rename":
        return df.rename(columns=config.get("mapping", {})).copy()
    if op == "add_constant":
        if not new_col:
            raise ValueError("New column name is required")
        out = df.copy()
        out[new_col] = config.get("value", "")
        return out
    if op == "formula":
        if not new_col:
            raise ValueError("New column name is required")
        expr = (config.get("expr") or "").strip()
        if not expr:
            raise ValueError("Formula is required")
        local_vars = _formula_env(df, config.get("numeric_mode", True))
        out = df.copy()
        out[new_col] = eval(compile(expr, "<datalab-formula>", "eval"), {"__builtins__": {}}, local_vars)
        return out
    if op == "fillna":
        if not cols:
            raise ValueError("Select at least one column")
        out = df.copy()
        for c in cols:
            out[c] = out[c].replace("", np.nan).fillna(config.get("value", ""))
        return out
    if op == "typecast":
        if not cols:
            raise ValueError("Select at least one column")
        out = df.copy()
        dtype = config.get("dtype", "string")
        for c in cols:
            if dtype == "numeric":
                out[c] = _coerce_numeric(out[c])
            elif dtype == "datetime":
                out[c] = pd.to_datetime(out[c], errors="coerce")
            else:
                out[c] = out[c].astype("string")
        return out
    raise ValueError(f"Unsupported operation: {op}")


def _truthy_mask(value, index) -> pd.Series:
    if isinstance(value, pd.Series):
        mask = value.reindex(index)
    elif isinstance(value, np.ndarray):
        mask = pd.Series(value, index=index)
    elif isinstance(value, list):
        mask = pd.Series(value, index=index)
    else:
        mask = pd.Series(bool(value), index=index)
    return mask.fillna(False).astype(bool)


def _normalize_text_series(s: pd.Series, trim=True, case_sensitive=False, normalize_tr=False) -> pd.Series:
    out = s.astype("string").fillna("")
    if trim:
        out = out.str.strip()
    if normalize_tr:
        trans = str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")
        out = out.apply(lambda x: str(x).translate(trans))
    if not case_sensitive:
        out = out.str.lower()
    return out


def _ready_cols(config, key="columns"):
    cols = config.get(key) or config.get("cols") or []
    if isinstance(cols, str):
        cols = [cols] if cols else []
    return [c for c in cols if c]


def _combine_masks(masks, index, method="any"):
    masks = [m.fillna(False).astype(bool) for m in masks]
    if not masks:
        return pd.Series(False, index=index)
    if method in {"all", "all_match"}:
        mask = pd.Series(True, index=index)
        for m in masks:
            mask &= m
        return mask
    mask = pd.Series(False, index=index)
    for m in masks:
        mask |= m
    return mask


def _matched_helpers(df, cols, masks, filter_name, reason=""):
    matched_col = pd.Series("", index=df.index, dtype="object")
    matched_val = pd.Series("", index=df.index, dtype="object")
    for col, mask in zip(cols, masks):
        fill = mask & matched_col.eq("")
        matched_col.loc[fill] = col
        matched_val.loc[fill] = df.loc[fill, col].astype("string").fillna("")
    return pd.DataFrame({
        "Eşleşen Kolon": matched_col,
        "Eşleşen Değer": matched_val,
        "Eşleşme Nedeni": reason,
        "Filtre Adı": filter_name,
        "Kontrol Sonucu": np.where(matched_col.ne(""), "Eşleşti", "Kontrol edildi"),
    }, index=df.index)


def _with_helpers(df, mask, helpers=None, include_helpers=True):
    out = df.loc[mask].copy()
    if include_helpers and helpers is not None and not helpers.empty:
        for col in helpers.columns:
            out[col] = helpers.loc[out.index, col].values
    return out


def _apply_debit_credit_split_filter(df: pd.DataFrame, params: dict, filter_name: str, include_helpers=True) -> pd.DataFrame:
    amount_structure = str(params.get("amount_structure") or "single").lower()
    out = df.copy()

    if amount_structure == "separate":
        debit_col = params.get("debit_col")
        credit_col = params.get("credit_col")
        if debit_col not in df.columns or credit_col not in df.columns:
            raise ValueError("Borç ve Alacak ayrı kolonlarda seçeneği için Borç ve Alacak kolonlarını seçin")
        debit = _coerce_numeric(df[debit_col]).fillna(0)
        credit = _coerce_numeric(df[credit_col]).fillna(0)
        source_note = f"Ayrı kolonlar: {debit_col} / {credit_col}"
    else:
        amount_col = params.get("amount_col")
        if amount_col not in df.columns:
            raise ValueError("Tek tutar kolonunda seçeneği için tutar kolonunu seçin")
        amount = _coerce_numeric(df[amount_col]).fillna(0)
        direction = str(params.get("single_amount_direction") or "positive_debit").lower()
        if direction == "negative_debit":
            debit = amount.where(amount < 0, 0).abs()
            credit = amount.where(amount > 0, 0).abs()
            source_note = f"Tek kolon: {amount_col}; negatif=borç, pozitif=alacak"
        else:
            debit = amount.where(amount > 0, 0).abs()
            credit = amount.where(amount < 0, 0).abs()
            source_note = f"Tek kolon: {amount_col}; pozitif=borç, negatif=alacak"

    out["CALC_DEBIT"] = _finite_series(debit)
    out["CALC_CREDIT"] = _finite_series(credit)
    if include_helpers:
        out["Filtre Adı"] = filter_name
        out["Kontrol Sonucu"] = "Borç/Alacak kolonları hesaplandı"
        out["Eşleşme Nedeni"] = source_note
    return out


def _blank_mask_for_series(s, params):
    text = _normalize_text_series(
        s,
        trim=params.get("trim", True),
        case_sensitive=not params.get("ignore_case", True),
    )
    invalid = set(_parse_filter_values(params.get("invalid_values", ""), {"ignore_case": params.get("ignore_case", True)}))
    if params.get("placeholder_as_blank", True):
        invalid.update(["null", "n/a", "na", "none", ".", "-", "/", "?", "***"])
    mask = s.isna() if params.get("null_as_blank", True) else pd.Series(False, index=s.index)
    if params.get("empty_string_as_blank", True):
        mask |= text.eq("")
    if invalid:
        mask |= text.isin({str(v).lower() for v in invalid})
    if params.get("zero_as_blank", False):
        mask |= _coerce_numeric(s).eq(0)
    if params.get("invalid_dates_as_blank", False):
        mask |= _coerce_date(s).isna()
    return mask


def _comparison_frame(df, cols, params, method):
    if method == "combined_text":
        sep = params.get("separator", " ")
        parts = pd.DataFrame({c: _normalize_text_series(df[c], params.get("trim", True), False) for c in cols}, index=df.index)
        return parts.agg(lambda row: sep.join([str(v) for v in row if str(v) != ""]), axis=1)
    if method == "first_non_empty":
        out = pd.Series("", index=df.index, dtype="object")
        for c in cols:
            txt = _normalize_text_series(df[c], params.get("trim", True), False)
            out = out.mask(out.astype("string").eq(""), txt)
        return out
    return None


def _apply_ready_filter(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    filter_id = config.get("filter_id") or config.get("readyFilterId")
    filter_name = config.get("filter_name") or filter_id or "Hazir Filtre"
    params = config.get("params") or {}
    cols = [c for c in _ready_cols(config) if c in df.columns]
    method = config.get("column_method") or params.get("column_method") or "any"
    include_helpers = config.get("include_helpers", True)
    if not cols and filter_id not in {"journal_risk", "debit_credit_split", "debit_credit_imbalance", "split_transaction", "single_leg_voucher", "creator_approver_same", "user_intensity", "same_day_same_amount", "after_hours_high_amount"}:
        raise ValueError("Hazir filtre icin en az bir kolon secin")

    def text_masks(op, value="", values=None, reason=""):
        target_values = values if values is not None else value
        masks = []
        combined = _comparison_frame(df, cols, params, method)
        work_cols = ["Birleşik Kolon"] if combined is not None else cols
        series_list = [combined] if combined is not None else [df[c] for c in cols]
        for s in series_list:
            masks.append(_manual_filter_mask(pd.DataFrame({"_": s}), {
                "column": "_", "operator": op, "value": value, "values": target_values,
                "caseSensitive": params.get("case_sensitive", False),
                "options": {"dedupe": True, "trim": True, "drop_empty": True, "ignore_case": not params.get("case_sensitive", False)},
            }))
        helpers = _matched_helpers(df, cols if combined is None else work_cols, masks, filter_name, reason)
        return _combine_masks(masks, df.index, method), helpers

    def numeric_masks(op, value="", value2="", reason=""):
        if method == "row_sum":
            s = sum((_coerce_numeric(df[c]) for c in cols), pd.Series(0.0, index=df.index))
            masks = [_manual_filter_mask(pd.DataFrame({"_": s}), {"column": "_", "operator": op, "value": value, "value2": value2, "dataType": "numeric"})]
            return masks[0], _matched_helpers(df, ["Satır Toplamı"], masks, filter_name, reason)
        if method == "row_diff" and len(cols) >= 2:
            s = _coerce_numeric(df[cols[0]]) - sum((_coerce_numeric(df[c]) for c in cols[1:]), pd.Series(0.0, index=df.index))
            masks = [_manual_filter_mask(pd.DataFrame({"_": s}), {"column": "_", "operator": op, "value": value, "value2": value2, "dataType": "numeric"})]
            return masks[0], _matched_helpers(df, ["Satır Farkı"], masks, filter_name, reason)
        masks = [_manual_filter_mask(df, {"column": c, "operator": op, "value": value, "value2": value2, "dataType": "numeric"}) for c in cols]
        return _combine_masks(masks, df.index, method), _matched_helpers(df, cols, masks, filter_name, reason)

    if method == "compare_columns" and len(cols) >= 2:
        texts = [_normalize_text_series(df[c], True, False) for c in cols]
        base = texts[0]
        equal = pd.Series(True, index=df.index)
        for s in texts[1:]:
            equal &= base.eq(s)
        mask = ~equal if params.get("comparison", "different") == "different" else equal
        helpers = pd.DataFrame({"Filtre Adı": filter_name, "Kontrol Sonucu": np.where(mask, "Kolonlar karşılaştırıldı", "")}, index=df.index)
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id == "debit_credit_split":
        return _apply_debit_credit_split_filter(df, params, filter_name, include_helpers)

    if filter_id in {"empty_document", "empty_description"}:
        filter_id = "empty"

    if filter_id in {"contains_word", "not_contains_word", "manual_entries", "special_chars_description"}:
        if filter_id == "special_chars_description":
            op, value, values, reason = "regex", r"[^a-zA-Z0-9ığüşöçİĞÜŞÖÇ\s.,;:!?/\-]", None, "Ozel karakter kontrolu"
        else:
            keywords = params.get("keywords") or ("manuel\nmanual\nMNL" if filter_id == "manual_entries" else "")
            words = _parse_filter_values(keywords)
            pattern = "|".join(re.escape(v) for v in words if v) or ".*"
            op = "regex_not" if filter_id == "not_contains_word" else "regex"
            value, values, reason = pattern, None, "Kelime listesi kontrolu"
        mask, helpers = text_masks(op, value, values, reason)
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"amount_between", "high_amount"}:
        if filter_id == "high_amount":
            value = params.get("min_amount", params.get("threshold", 100000))
            mask, helpers = numeric_masks("gte", value, reason="Yuksek tutar")
        else:
            lo = params.get("min_amount", "")
            hi = params.get("max_amount", "")
            mask, helpers = numeric_masks("between", lo, hi, "Tutar araligi")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"date_range", "date_set", "month_end", "year_end"}:
        masks = []
        if filter_id == "date_set":
            values = [_date_scalar(v).normalize() for v in _parse_filter_values(params.get("date_values", ""))]
            values = [v for v in values if not pd.isna(v)]
            for c in cols:
                masks.append(_coerce_date(df[c]).dt.normalize().isin(values))
            reason = "Tarih listesi"
        elif filter_id == "month_end":
            for c in cols:
                masks.append(_coerce_date(df[c]).dt.is_month_end.fillna(False))
            reason = "Ay sonu"
        elif filter_id == "year_end":
            for c in cols:
                dt = _coerce_date(df[c])
                masks.append((dt.dt.month.eq(12) & dt.dt.day.eq(31)).fillna(False))
            reason = "Yil sonu"
        else:
            for c in cols:
                m = _date_range_mask(
                    df[c],
                    params.get("start_date"),
                    params.get("end_date"),
                    params.get("ignore_time", True),
                )
                masks.append(~m if params.get("outside", False) else m)
            reason = "Tarih araligi"
        mask = _combine_masks(masks, df.index, method)
        helpers = _matched_helpers(df, cols, masks, filter_name, reason)
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"account_groups", "account_prefix"}:
        filter_id = "account_codes"

    if filter_id == "account_range":
        start = int(float(params.get("start_account", 0) or 0))
        end = int(float(params.get("end_account", 999999999) or 999999999))
        prefix_len = int(float(params.get("prefix_len", 3) or 3))
        masks = []
        for c in cols:
            text = _normalize_text_series(df[c], True, False).str.replace(r"[^0-9]", "", regex=True).str[:prefix_len]
            num = pd.to_numeric(text, errors="coerce")
            masks.append(num.between(start, end))
        mask = _combine_masks(masks, df.index, method)
        helpers = _matched_helpers(df, cols, masks, filter_name, "Hesap kodu araligi")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"duplicate_amount", "same_day_same_amount"}:
        if filter_id == "same_day_same_amount":
            date_col = params.get("date_col")
            amount_col = params.get("amount_col")
            if date_col not in df.columns or amount_col not in df.columns:
                raise ValueError("Tarih ve tutar kolonlari secilmeli")
            keys = pd.DataFrame({
                "date": _coerce_date(df[date_col]).dt.normalize().astype("string").fillna(""),
                "amount": _coerce_numeric(df[amount_col]).round(int(params.get("decimal_precision", 2) or 2)).astype("string").fillna(""),
            }, index=df.index)
        else:
            keys = pd.DataFrame({c: _coerce_numeric(df[c]).round(int(params.get("decimal_precision", 2) or 2)).astype("string").fillna("") for c in cols}, index=df.index)
        key = keys.agg("\u001f".join, axis=1)
        counts = key.groupby(key, dropna=False).transform("size")
        mask = counts.ge(int(float(params.get("min_count", 2) or 2)))
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Duplicate Sayısı"] = counts.loc[mask].values
            out["Duplicate Grup Numarası"] = pd.Series(key.factorize()[0] + 1, index=df.index).loc[mask].values
        return out

    if filter_id == "rare_user_transactions":
        keys = pd.DataFrame({c: _normalize_text_series(df[c], True, False) for c in cols}, index=df.index)
        key = keys.agg("\u001f".join, axis=1)
        counts = key.groupby(key, dropna=False).transform("size")
        mask = counts.le(int(float(params.get("max_count", 3) or 3)))
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Duplicate Sayısı"] = counts.loc[mask].values
            out["Risk Seviyesi"] = "Orta"
        return out

    if filter_id == "after_hours_high_amount":
        date_col = params.get("datetime_col")
        amount_col = params.get("amount_col")
        if date_col not in df.columns or amount_col not in df.columns:
            raise ValueError("Tarih-saat ve tutar kolonlari secilmeli")
        start = str(params.get("work_start", "08:00"))
        end = str(params.get("work_end", "18:00"))
        dt = _coerce_date(df[date_col])
        minutes = dt.dt.hour * 60 + dt.dt.minute
        s_min = int(start[:2]) * 60 + int(start[-2:])
        e_min = int(end[:2]) * 60 + int(end[-2:])
        if s_min <= e_min:
            time_mask = minutes.lt(s_min) | minutes.gt(e_min)
        else:
            time_mask = ~(minutes.ge(s_min) | minutes.le(e_min))
        amount_mask = _coerce_numeric(df[amount_col]).abs().ge(_safe_float(params.get("min_amount", 100000), 100000))
        mask = time_mask.fillna(False) & amount_mask.fillna(False)
        helpers = _matched_helpers(df, [date_col, amount_col], [mask, mask], filter_name, "Mesai disi yuksek tutar")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"empty", "not_empty"}:
        masks = [_blank_mask_for_series(df[c], params) for c in cols]
        mask = _combine_masks(masks, df.index, method if filter_id == "empty" else params.get("filled_method", method))
        if filter_id == "not_empty":
            mask = _combine_masks([~m for m in masks], df.index, method)
            min_len = int(float(params.get("min_len", 1) or 1))
            if min_len > 1:
                len_masks = [_normalize_text_series(df[c], params.get("trim", True), False).str.len().ge(min_len) for c in cols]
                mask &= _combine_masks(len_masks, df.index, method)
        helpers = _matched_helpers(df, cols, masks if filter_id == "empty" else [~m for m in masks], filter_name, "Boş/dolu değer kontrolü")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"duplicates", "unique"}:
        case_sensitive = params.get("case_sensitive", False)
        trim = params.get("trim", True)
        keys = pd.DataFrame({c: _normalize_text_series(df[c], trim, case_sensitive, params.get("normalize_tr", False)) for c in cols})
        dup_all = keys.duplicated(keep=False)
        group_key = keys.astype("string").agg("\u001f".join, axis=1)
        dup_count = group_key.groupby(group_key, dropna=False).transform("size") if len(cols) else pd.Series(0, index=df.index)
        min_count = int(float(params.get("min_count", 2) or 2))
        if params.get("keep_mode") == "second":
            mask = keys.duplicated(keep="first")
        elif params.get("keep_mode") == "first":
            mask = keys.duplicated(keep="last")
        else:
            mask = dup_all
        mask &= dup_count.ge(min_count)
        if filter_id == "unique":
            mask = ~dup_all
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Duplicate Sayısı"] = dup_count.loc[mask].values
            out["Duplicate Grup Numarası"] = pd.Series(group_key.factorize()[0] + 1, index=df.index).loc[mask].values
            out["Kontrol Sonucu"] = "Duplicate" if filter_id == "duplicates" else "Benzersiz"
        return out

    if filter_id in {"negative", "zero", "top_n", "bottom_n", "random_n", "round_amounts"}:
        if filter_id == "negative":
            threshold = params.get("threshold", "")
            op = "lt" if threshold not in {"", None} else "negative"
            mask, helpers = numeric_masks(op, threshold, reason="Negatif tutar")
        elif filter_id == "zero":
            tol = _safe_float(params.get("tolerance", 0), 0)
            mask, helpers = numeric_masks("between", -tol, tol, "Sıfır/tolerans kontrolü")
            if not params.get("null_as_zero", False):
                mask &= _combine_masks([_coerce_numeric(df[c]).notna() for c in cols], df.index, method)
        elif filter_id == "round_amounts":
            multiple = abs(_safe_float(params.get("multiple", 1000), 1000)) or 1000
            min_amount = _safe_float(params.get("min_amount", 0), 0)
            masks = []
            for c in cols:
                s = _coerce_numeric(df[c]).abs() if params.get("absolute", True) else _coerce_numeric(df[c])
                masks.append(s.ge(min_amount) & np.isclose(s % multiple, 0, atol=1e-9))
            mask = _combine_masks(masks, df.index, method)
            helpers = _matched_helpers(df, cols, masks, filter_name, f"{multiple:g} katı yuvarlak tutar")
        else:
            n = params.get("n") or config.get("n") or 10
            op = {"top_n": "top_n", "bottom_n": "bottom_n", "random_n": "random_n"}[filter_id]
            mask, helpers = numeric_masks(op, n, reason=f"{filter_name} N={n}")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"weekend", "date_between", "period_end"}:
        if filter_id == "weekend":
            masks = [_manual_filter_mask(df, {"column": c, "operator": "weekend"}) for c in cols]
            mask = _combine_masks(masks, df.index, method)
            helpers = _matched_helpers(df, cols, masks, filter_name, "Hafta sonu tarih")
        elif filter_id == "period_end":
            end = _date_scalar(params.get("period_end") or pd.Timestamp.today())
            before = int(float(params.get("days_before", 7) or 7))
            after = int(float(params.get("days_after", 0) or 0))
            masks = []
            for c in cols:
                dt = _coerce_date(df[c])
                masks.append(dt.between(end - pd.Timedelta(days=before), end + pd.Timedelta(days=after)))
            mask = _combine_masks(masks, df.index, method)
            helpers = _matched_helpers(df, cols, masks, filter_name, "Dönem sonu aralığı")
        else:
            masks = [
                _date_range_mask(
                    df[c],
                    params.get("start_date"),
                    params.get("end_date"),
                    params.get("ignore_time", True),
                )
                for c in cols
            ]
            mask = _combine_masks(masks, df.index, method)
            helpers = _matched_helpers(df, cols, masks, filter_name, "Belirli tarih aralığı")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"after_hours"}:
        start = str(params.get("work_start", "08:00"))
        end = str(params.get("work_end", "18:00"))
        masks = []
        for c in cols:
            dt = _coerce_date(df[c])
            minutes = dt.dt.hour * 60 + dt.dt.minute
            s_min = int(start[:2]) * 60 + int(start[-2:])
            e_min = int(end[:2]) * 60 + int(end[-2:])
            if s_min <= e_min:
                m = minutes.lt(s_min) | minutes.gt(e_min)
            else:
                m = ~(minutes.ge(s_min) | minutes.le(e_min))
            if params.get("weekend_as_after_hours", True):
                m |= dt.dt.weekday.isin([5, 6])
            masks.append(m.fillna(False))
        mask = _combine_masks(masks, df.index, method)
        helpers = _matched_helpers(df, cols, masks, filter_name, "Mesai dışı kayıt")
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"short_text", "suspicious_keywords", "voucher", "users", "exclude_opening", "account_codes", "generic_system_user"}:
        if filter_id == "short_text":
            op, value, values, reason = "len_lt", params.get("max_len") or params.get("n") or 5, None, "Kısa açıklama"
        elif filter_id == "exclude_opening":
            values = _parse_filter_values(params.get("exclude_words") or "acilis,açılış,devir,opening")
            pattern = "|".join(re.escape(v) for v in values if v) or "acilis|açılış|devir|opening"
            combined = _comparison_frame(df, cols, params, method)
            work_cols = ["Birleşik Kolon"] if combined is not None else cols
            series_list = [combined] if combined is not None else [df[c] for c in cols]
            masks = []
            for s in series_list:
                text = _normalize_text_series(s, params.get("trim", True), params.get("case_sensitive", False), params.get("normalize_tr", True))
                masks.append(text.str.contains(pattern.lower(), regex=True, na=False))
            opening_mask = _combine_masks(masks, df.index, method)
            helpers = _matched_helpers(df, work_cols, masks, filter_name, "Açılış/devir kaydı hariç tutuldu")
            return _with_helpers(df, ~opening_mask, helpers, include_helpers)
        elif filter_id == "account_codes":
            values = _parse_filter_values(params.get("include_accounts", params.get("values", "")))
            prefix_len = int(float(params.get("prefix_len", 0) or 0))
            pattern = "|".join(re.escape(v[:prefix_len] if prefix_len else v) for v in values) or ".*"
            op, value, reason = "regex", f"^(?:{pattern})", "Hesap kodu eşleşmesi"
        elif filter_id == "suspicious_keywords":
            values = _parse_filter_values(params.get("keywords", "düzeltme,correction,manuel,manual,bonus,ikramiye,hediye,gift,acil,urgent,özel,fark,adjustment,misc,miscellaneous,diğer,geçici,avans,emanet,iptal,geri ödeme"))
            op, value, reason = "regex", "|".join(re.escape(v) for v in values), "Şüpheli anahtar kelime"
        elif filter_id == "generic_system_user":
            values = _parse_filter_values(params.get("patterns", "admin,administrator,system,service,sa,root,test,user,generic"))
            op, value, reason = "regex", "|".join(re.escape(v) for v in values), "Generic/sistem kullanıcısı"
        else:
            op, value, values, reason = "in", "", params.get("values") or params.get("include_values", ""), f"{filter_name} liste kontrolü"
        mask, helpers = text_masks(op, value, values, reason)
        return _with_helpers(df, mask, helpers, include_helpers)

    if filter_id in {"revenue_counter_account", "opex_counter_account", "inventory_counter_account", "asset_account_control", "unusual_account_combo", "rare_account_combo"}:
        account_col = params.get("account_col") or (cols[0] if cols else "")
        counter_col = params.get("counter_account_col") or (cols[1] if len(cols) > 1 else "")
        if account_col not in df.columns:
            raise ValueError("Hesap kolonu secilmedi")
        accounts = _parse_filter_values(params.get("accounts") or params.get("main_accounts") or "600,601,602,610,611")
        expected = _parse_filter_values(params.get("expected_accounts") or "100,101,102,120,121,127,150,153,157,181,281,320,380,391,480,620,646,654,689,710,712,720,721,730,731,760,770,771,800")
        acc = _normalize_text_series(df[account_col], True, False)
        acc_mask = pd.Series(False, index=df.index)
        for a in accounts:
            acc_mask |= acc.str.startswith(str(a).lower(), na=False)
        if counter_col in df.columns:
            ctr = _normalize_text_series(df[counter_col], True, False)
            ctr_ok = pd.Series(False, index=df.index)
            for e in expected:
                ctr_ok |= ctr.str.startswith(str(e).lower(), na=False)
            mask = acc_mask & ~ctr_ok
            combo = acc.astype(str) + " / " + ctr.astype(str)
        else:
            mask = acc_mask
            combo = acc.astype(str)
        if filter_id == "rare_account_combo":
            counts = combo.groupby(combo).transform("size")
            mask = counts.le(int(float(params.get("max_count", 1) or 1)))
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Hesap Kombinasyonu"] = combo.loc[mask].values
            out["Eşleşme Nedeni"] = "Beklenen karşı hesap dışında çalışma"
            out["Risk Seviyesi"] = "Yüksek"
        return out

    if filter_id in {"duplicate_invoice_payment", "reversal_check"}:
        key_cols = cols or [p for p in [params.get("invoice_col"), params.get("document_col"), params.get("supplier_col"), params.get("amount_col")] if p in df.columns]
        if not key_cols:
            raise ValueError("Duplicate kontrolu icin kolon secin")
        tmp = pd.DataFrame(index=df.index)
        for c in key_cols:
            if c == params.get("amount_col") or str(c).lower() in {"tutar", "amount", "borc", "alacak"}:
                vals = _coerce_numeric(df[c]).abs() if filter_id == "reversal_check" else _coerce_numeric(df[c]).round(int(params.get("decimal_precision", 2) or 2))
                tmp[c] = vals.astype("string").fillna("")
            else:
                tmp[c] = _normalize_text_series(df[c], True, False)
        key = tmp.agg("\u001f".join, axis=1)
        counts = key.groupby(key, dropna=False).transform("size")
        mask = counts.ge(int(float(params.get("min_count", 2) or 2)))
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Duplicate Sayısı"] = counts.loc[mask].values
            out["Duplicate Grup Numarası"] = pd.Series(key.factorize()[0] + 1, index=df.index).loc[mask].values
            out["Risk Seviyesi"] = "Yüksek"
        return out

    if filter_id == "document_sequence_gap":
        doc_col = params.get("document_col") or (cols[0] if cols else "")
        if doc_col not in df.columns:
            raise ValueError("Belge numarasi kolonu secilmeli")
        text = _normalize_text_series(df[doc_col], True, False)
        counts = text.groupby(text, dropna=False).transform("size")
        mask = text.eq("") | counts.gt(1)
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Duplicate Sayısı"] = counts.loc[mask].values
            out["Kontrol Sonucu"] = "Bos veya mukerrer belge numarasi"
            out["Risk Seviyesi"] = "Orta"
        return out

    if filter_id == "split_transaction":
        amount_col = params.get("amount_col") or (cols[0] if cols else "")
        group_cols = [c for c in [params.get("supplier_col"), params.get("user_col"), params.get("account_col"), params.get("date_col")] if c in df.columns]
        if amount_col not in df.columns or not group_cols:
            raise ValueError("Bolunmus islem icin tutar ve en az bir grup kolonu secin")
        limit = _safe_float(params.get("limit_amount", 100000), 100000)
        amounts = _coerce_numeric(df[amount_col]).abs()
        tmp = df[group_cols].copy()
        date_col = params.get("date_col")
        if date_col in tmp.columns:
            tmp[date_col] = _coerce_date(tmp[date_col]).dt.normalize()
        group_key = tmp.astype("string").fillna("").agg("\u001f".join, axis=1)
        group_total = amounts.groupby(group_key, dropna=False).transform("sum")
        group_size = amounts.groupby(group_key, dropna=False).transform("size")
        mask = amounts.lt(limit) & group_total.ge(limit) & group_size.ge(int(params.get("min_parts", 2) or 2))
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Sapma Tutarı"] = group_total.loc[mask].values
            out["Duplicate Grup Numarası"] = pd.Series(group_key.factorize()[0] + 1, index=df.index).loc[mask].values
            out["Risk Seviyesi"] = "Yüksek"
        return out

    if filter_id == "single_leg_voucher":
        voucher_col = params.get("voucher_col")
        debit_col = params.get("debit_col")
        credit_col = params.get("credit_col")
        if voucher_col not in df.columns:
            raise ValueError("Fis numarasi kolonu secilmeli")
        rows = df.groupby(voucher_col, dropna=False)[voucher_col].transform("size")
        mask = rows.le(int(params.get("min_rows", 1) or 1))
        if debit_col in df.columns and credit_col in df.columns:
            debit = _coerce_numeric(df[debit_col]).fillna(0)
            credit = _coerce_numeric(df[credit_col]).fillna(0)
            debit_sum = debit.groupby(df[voucher_col], dropna=False).transform("sum")
            credit_sum = credit.groupby(df[voucher_col], dropna=False).transform("sum")
            mask |= (debit_sum.gt(0) & credit_sum.eq(0)) | (credit_sum.gt(0) & debit_sum.eq(0))
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Kontrol Sonucu"] = "Tek bacakli fis"
            out["Risk Seviyesi"] = "Yüksek"
        return out

    if filter_id == "creator_approver_same":
        creator = params.get("creator_col")
        approver = params.get("approver_col")
        if creator not in df.columns or approver not in df.columns:
            raise ValueError("Olusturan ve onaylayan kolonlari secilmeli")
        left = _normalize_text_series(df[creator], True, False)
        right = _normalize_text_series(df[approver], True, False)
        if params.get("strip_domain", True):
            left = left.str.replace(r"^.*\\", "", regex=True).str.replace(r"@.*$", "", regex=True)
            right = right.str.replace(r"^.*\\", "", regex=True).str.replace(r"@.*$", "", regex=True)
        mask = left.ne("") & left.eq(right)
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Kontrol Sonucu"] = "Olusturan ve onaylayan ayni"
            out["Risk Seviyesi"] = "Yüksek"
        return out

    if filter_id == "user_intensity":
        user_col = params.get("user_col") or (cols[0] if cols else "")
        amount_col = params.get("amount_col")
        if user_col not in df.columns:
            raise ValueError("Kullanici kolonu secilmeli")
        users = _normalize_text_series(df[user_col], True, False)
        counts = users.groupby(users, dropna=False).transform("size")
        mask = counts.ge(int(params.get("min_count", 100) or 100))
        if amount_col in df.columns:
            totals = _coerce_numeric(df[amount_col]).abs().groupby(users, dropna=False).transform("sum")
            threshold = _safe_float(params.get("amount_threshold", np.inf), np.inf)
            mask |= totals.ge(threshold)
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Kontrol Sonucu"] = "Kullanici yogunluk analizi"
            out["Duplicate Sayısı"] = counts.loc[mask].values
            out["Risk Seviyesi"] = "Orta"
        return out

    if filter_id == "debit_credit_imbalance":
        group_col = params.get("voucher_col") or (cols[0] if cols else "")
        debit_col = params.get("debit_col")
        credit_col = params.get("credit_col")
        if group_col not in df.columns or debit_col not in df.columns or credit_col not in df.columns:
            raise ValueError("Fiş, borç ve alacak kolonları seçilmeli")
        tmp = pd.DataFrame({"g": df[group_col], "d": _coerce_numeric(df[debit_col]), "c": _coerce_numeric(df[credit_col])}, index=df.index)
        totals = tmp.groupby("g", dropna=False).agg(Borç_Toplamı=("d", "sum"), Alacak_Toplamı=("c", "sum"))
        totals["Fark"] = totals["Borç_Toplamı"] - totals["Alacak_Toplamı"]
        bad = totals[totals["Fark"].abs().gt(_safe_float(params.get("tolerance", 0), 0))]
        out = df[df[group_col].isin(bad.index)].copy()
        if include_helpers:
            out = out.merge(bad.reset_index().rename(columns={"g": group_col}), on=group_col, how="left")
            out["Filtre Adı"] = filter_name
            out["Risk Seviyesi"] = np.where(out["Fark"].abs() > 1000, "Yüksek", "Orta")
        return out

    if filter_id == "benford":
        amount_col = cols[0]
        s = _coerce_numeric(df[amount_col]).abs()
        s = s[s.gt(_safe_float(params.get("min_amount", 0), 0))]
        first_digit = s.astype("Int64").astype("string").str.replace(r"[^1-9]", "", regex=True).str[0]
        counts = first_digit.value_counts(normalize=True)
        risky_digits = counts[counts.sub(pd.Series({str(i): math.log10(1 + 1 / i) for i in range(1, 10)})).abs().gt(0.08)].index
        mask = first_digit.reindex(df.index).isin(risky_digits).fillna(False)
        out = df.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Sapma Yüzdesi"] = first_digit.reindex(out.index).map(counts).fillna(0).values
            out["Risk Seviyesi"] = "Orta"
        return out

    if filter_id == "journal_risk":
        out = df.copy()
        score = pd.Series(0, index=df.index)
        notes = []
        amount_col = params.get("amount_col")
        desc_col = params.get("description_col")
        user_col = params.get("user_col")
        date_col = params.get("datetime_col")
        if amount_col in df.columns:
            score += _coerce_numeric(df[amount_col]).abs().gt(_safe_float(params.get("high_amount", 100000), 100000)).astype(int) * int(params.get("high_amount_score", 30))
        if desc_col in df.columns:
            score += _normalize_text_series(df[desc_col], True, False).str.len().lt(int(params.get("short_desc_len", 5))).astype(int) * int(params.get("short_desc_score", 15))
        if user_col in df.columns:
            score += _normalize_text_series(df[user_col], True, False).str.contains("admin|system|service|root|test|generic", regex=True, na=False).astype(int) * int(params.get("generic_user_score", 25))
        if date_col in df.columns:
            dt = _coerce_date(df[date_col])
            score += dt.dt.weekday.isin([5, 6]).fillna(False).astype(int) * int(params.get("weekend_score", 20))
        mask = score.ge(int(params.get("min_score", 20)))
        out = out.loc[mask].copy()
        if include_helpers:
            out["Filtre Adı"] = filter_name
            out["Risk Skoru"] = score.loc[mask].values
            out["Risk Seviyesi"] = pd.cut(score.loc[mask], bins=[-1, 20, 50, 80, 10**9], labels=["Düşük", "Orta", "Yüksek", "Kritik"]).astype(str).values
            out["İnceleme Notu"] = "Otomatik risk skoru"
        return out

    raise ValueError(f"Desteklenmeyen hazir filtre: {filter_id}")


def _apply_ready_filter_chain(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    chain = []
    for item in config.get("chain", []):
        cfg = item.get("config") if isinstance(item, dict) and item.get("config") else item
        if isinstance(cfg, dict) and cfg.get("op") == "ready_filter":
            chain.append(cfg)
    if not chain:
        raise ValueError("Filtre zinciri bos")

    logic = str(config.get("chain_logic") or "and").lower()
    if logic == "or":
        pieces = []
        for cfg in chain:
            piece = _apply_ready_filter(df, cfg)
            if piece is not None and not piece.empty:
                pieces.append(piece)
        if not pieces:
            return df.iloc[0:0].copy()
        out = pd.concat(pieces, axis=0, sort=False)
        return out.loc[~out.index.duplicated(keep="first")].sort_index()

    current = df.copy()
    for cfg in chain:
        current = _apply_ready_filter(current, cfg)
    return current


def _parse_filter_values(value, options=None):
    options = options or {}
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[\n\r,;\t]+", str(value or ""))
    out = []
    for item in parts:
        text = str(item)
        if options.get("trim", True):
            text = text.strip()
        if options.get("drop_empty", True) and text == "":
            continue
        out.append(text)
    if options.get("dedupe", True):
        seen = set()
        deduped = []
        for item in out:
            key = item.lower() if options.get("ignore_case", True) else item
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        out = deduped
    return out


def _coerce_date(values) -> pd.Series:
    s = values if isinstance(values, pd.Series) else pd.Series(values)
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce")

    try:
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True, format="mixed")
    except TypeError:
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)

    text_values = s.astype("string").str.strip()
    iso_mask = text_values.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", na=False)
    if iso_mask.any():
        try:
            parsed_iso = pd.to_datetime(s[iso_mask], errors="coerce", dayfirst=False, format="mixed")
        except TypeError:
            parsed_iso = pd.to_datetime(s[iso_mask], errors="coerce", dayfirst=False)
        parsed.loc[iso_mask] = parsed_iso

    missing = parsed.isna() & s.notna()
    if missing.any():
        try:
            parsed_alt = pd.to_datetime(s[missing], errors="coerce", dayfirst=False, format="mixed")
        except TypeError:
            parsed_alt = pd.to_datetime(s[missing], errors="coerce", dayfirst=False)
        parsed.loc[missing] = parsed_alt

    missing = parsed.isna() & s.notna()
    if missing.any():
        numeric = pd.to_numeric(s[missing], errors="coerce")
        excel_like = numeric.notna() & numeric.between(1, 2958465)
        if excel_like.any():
            excel_dates = pd.to_datetime(
                numeric[excel_like],
                errors="coerce",
                unit="D",
                origin="1899-12-30",
            )
            parsed.loc[numeric[excel_like].index] = excel_dates
    return parsed


def _date_scalar(value):
    text = str(value or "").strip()
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text):
        return pd.to_datetime(text, errors="coerce", dayfirst=False)
    try:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True, format="mixed")
    except TypeError:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        try:
            parsed = pd.to_datetime(value, errors="coerce", dayfirst=False, format="mixed")
        except TypeError:
            parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
    return parsed


def _date_range_mask(values, start_value, end_value, ignore_time=True):
    dt = _coerce_date(values)
    start = _date_scalar(start_value)
    end = _date_scalar(end_value)
    if pd.isna(start) or pd.isna(end):
        return pd.Series(False, index=dt.index)
    if start > end:
        start, end = end, start
    if ignore_time:
        return dt.dt.normalize().between(start.normalize(), end.normalize(), inclusive="both").fillna(False)
    return dt.between(start, end, inclusive="both").fillna(False)


def _week_bounds(now=None, offset=0):
    today = pd.Timestamp(now or pd.Timestamp.today()).normalize()
    start = today - pd.Timedelta(days=today.weekday()) + pd.Timedelta(days=offset * 7)
    return start, start + pd.Timedelta(days=6, hours=23, minutes=59, seconds=59)


def _manual_filter_mask(df: pd.DataFrame, condition: dict) -> pd.Series:
    if condition.get("enabled") is False:
        return pd.Series(True, index=df.index)
    col = condition.get("column")
    op = condition.get("operator", "contains")
    value = condition.get("value", "")
    value2 = condition.get("value2", "")
    data_type = str(condition.get("dataType") or condition.get("dtype") or "").lower()
    if col not in df.columns:
        raise ValueError(f"Column not found: {col}")

    raw = df[col]
    text = raw.astype("string").fillna("")
    case_sensitive = bool(condition.get("caseSensitive", False))
    text_cmp = text if case_sensitive else text.str.lower()
    val = str(value)
    val_cmp = val if case_sensitive else val.lower()
    options = condition.get("options") or {}

    numeric = _coerce_numeric(raw)
    target = _safe_float(_coerce_numeric([value]).iloc[0], default=np.nan)
    target2 = _safe_float(_coerce_numeric([value2]).iloc[0], default=np.nan)
    if data_type == "numeric" and op == "equals":
        return numeric.eq(target)
    if data_type == "numeric" and op == "not_equals":
        return numeric.ne(target) & numeric.notna()

    if op == "contains":
        return text_cmp.str.contains(re.escape(val_cmp), na=False)
    if op == "not_contains":
        return ~text_cmp.str.contains(re.escape(val_cmp), na=False)
    if op == "equals":
        return text_cmp.eq(val_cmp)
    if op == "not_equals":
        return ~text_cmp.eq(val_cmp)
    if op == "starts":
        return text_cmp.str.startswith(val_cmp, na=False)
    if op == "ends":
        return text_cmp.str.endswith(val_cmp, na=False)
    if op == "regex":
        return text.str.contains(val, regex=True, case=case_sensitive, na=False)
    if op == "regex_not":
        return ~text.str.contains(val, regex=True, case=case_sensitive, na=False)
    if op in {"in", "not_in"}:
        values = _parse_filter_values(condition.get("values", value), options)
        if not case_sensitive or options.get("ignore_case", False):
            values = [v.lower() for v in values]
            mask = text.str.lower().isin(values)
        else:
            mask = text.isin(values)
        return ~mask if op == "not_in" else mask
    if op == "is_empty":
        return text.eq("")
    if op == "not_empty":
        return text.ne("")
    if op == "len_eq":
        return text.str.len().eq(int(float(value)))
    if op == "len_lt":
        return text.str.len().lt(int(float(value)))
    if op == "len_gt":
        return text.str.len().gt(int(float(value)))
    if op == "duplicate":
        return raw.duplicated(keep=False)
    if op == "unique":
        return ~raw.duplicated(keep=False)

    if op == "gt":
        return numeric.gt(target)
    if op == "gte":
        return numeric.ge(target)
    if op == "lt":
        return numeric.lt(target)
    if op == "lte":
        return numeric.le(target)
    if op == "between":
        lo, hi = sorted([target, target2])
        return numeric.between(lo, hi)
    if op == "not_between":
        lo, hi = sorted([target, target2])
        return ~numeric.between(lo, hi)
    if op in {"num_in", "num_not_in"}:
        vals = _coerce_numeric(_parse_filter_values(condition.get("values", value), options)).dropna().tolist()
        mask = numeric.isin(vals)
        return ~mask if op == "num_not_in" else mask
    if op == "zero":
        return numeric.eq(0)
    if op == "non_zero":
        return numeric.ne(0) & numeric.notna()
    if op == "positive":
        return numeric.gt(0)
    if op == "negative":
        return numeric.lt(0)
    if op in {"top_n", "bottom_n"}:
        n = max(1, int(float(value or 10)))
        valid = numeric.dropna()
        idx = valid.nlargest(n).index if op == "top_n" else valid.nsmallest(n).index
        return pd.Series(df.index.isin(idx), index=df.index)
    if op == "random_n":
        n = min(len(df), max(1, int(float(value or 10))))
        idx = df.sample(n=n, random_state=42).index
        return pd.Series(df.index.isin(idx), index=df.index)

    dt = _coerce_date(raw)
    today = pd.Timestamp.today().normalize()
    if op in {"date_eq", "date_equals"}:
        target_dt = _date_scalar(value)
        return dt.dt.normalize().eq(target_dt.normalize() if not pd.isna(target_dt) else target_dt)
    if op == "date_before":
        return dt.lt(_date_scalar(value))
    if op == "date_after":
        return dt.gt(_date_scalar(value))
    if op == "date_on_or_after":
        return dt.ge(_date_scalar(value))
    if op == "date_on_or_before":
        return dt.le(_date_scalar(value))
    if op == "month":
        try:
            return dt.dt.month.eq(int(float(value)))
        except Exception:
            return pd.Series(False, index=df.index)
    if op == "year":
        try:
            return dt.dt.year.eq(int(float(value)))
        except Exception:
            return pd.Series(False, index=df.index)
    if op == "date_between":
        return _date_range_mask(raw, value, value2, options.get("ignore_time", True))
    if op == "today":
        return dt.dt.normalize().eq(today)
    if op == "yesterday":
        return dt.dt.normalize().eq(today - pd.Timedelta(days=1))
    if op == "this_week":
        start, end = _week_bounds(today)
        return dt.between(start, end)
    if op == "last_week":
        start, end = _week_bounds(today, offset=-1)
        return dt.between(start, end)
    if op == "this_month":
        return dt.dt.year.eq(today.year) & dt.dt.month.eq(today.month)
    if op == "last_month":
        last = today.replace(day=1) - pd.Timedelta(days=1)
        return dt.dt.year.eq(last.year) & dt.dt.month.eq(last.month)
    if op == "this_year":
        return dt.dt.year.eq(today.year)
    if op == "last_year":
        return dt.dt.year.eq(today.year - 1)
    if op == "last_n_days":
        n = max(0, int(float(value or 0)))
        return dt.ge(today - pd.Timedelta(days=n)) & dt.le(today + pd.Timedelta(days=1))
    if op == "first_n_days":
        n = max(1, int(float(value or 1)))
        first = dt.min()
        if pd.isna(first):
            return pd.Series(False, index=df.index)
        return dt.between(first, first + pd.Timedelta(days=n - 1))
    if op == "weekday":
        raw_day = str(value).strip().lower()
        day_map = {"pazartesi": 0, "sali": 1, "salı": 1, "carsamba": 2, "çarşamba": 2, "persembe": 3, "perşembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
        day = day_map.get(raw_day)
        if day is None:
            try:
                day = int(float(value))
            except Exception:
                day = None
        return dt.dt.weekday.eq(day) if day is not None else pd.Series(False, index=df.index)
    if op == "weekend":
        return dt.dt.weekday.isin([5, 6])

    bool_text = text.str.strip().str.lower()
    if op == "is_true":
        return bool_text.isin(["true", "1", "evet", "yes", "doğru", "dogru"])
    if op == "is_false":
        return bool_text.isin(["false", "0", "hayir", "hayır", "no", "yanlış", "yanlis"])

    raise ValueError(f"Unsupported filter operator: {op}")


def _filter_tree_mask(df: pd.DataFrame, node: dict, depth: int = 0) -> pd.Series:
    if depth > 5:
        raise ValueError("Filter group depth limit exceeded")
    if not node:
        return pd.Series(True, index=df.index)
    if node.get("type") == "condition" or "operator" in node:
        if node.get("enabled") is False:
            return pd.Series(True, index=df.index)
        return _manual_filter_mask(df, node)

    children = [child for child in (node.get("children") or []) if child]
    if not children:
        return pd.Series(True, index=df.index)
    logic = str(node.get("logic", "and")).lower()
    mask = pd.Series(False if logic == "or" else True, index=df.index)
    for child in children:
        cmask = _filter_tree_mask(df, child, depth + 1)
        mask = (mask | cmask) if logic == "or" else (mask & cmask)
    return mask


def _apply_filter(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    mode = config.get("mode", "manual")
    if mode == "formula":
        expr = (config.get("expr") or "").strip()
        if not expr:
            raise ValueError("Filter formula is required")
        env = _formula_env(df, numeric_mode=False)
        try:
            result = eval(compile(expr, "<datalab-filter>", "eval"), {"__builtins__": {}}, env)
        except SyntaxError:
            exec(compile(expr, "<datalab-filter>", "exec"), {"__builtins__": {}}, env)
            result = env.get("_filter", None)
            if result is None:
                result = env.get("mask", None)
            if result is None:
                raise ValueError("Python filtre kodu _filter veya mask degiskeni uretmeli")
        mask = _truthy_mask(result, df.index)
    elif config.get("filter_tree"):
        mask = _filter_tree_mask(df, config.get("filter_tree"))
    else:
        conditions = config.get("conditions") or []
        if not conditions:
            raise ValueError("At least one filter condition is required")
        logic = str(config.get("logic", "and")).lower()
        mask = pd.Series(True if logic != "or" else False, index=df.index)
        for condition in conditions:
            cmask = _manual_filter_mask(df, condition)
            if logic == "or":
                mask = mask | cmask
            else:
                mask = mask & cmask
    return df.loc[mask].copy()


def join_dataframes(left: pd.DataFrame, right: pd.DataFrame, config: dict) -> pd.DataFrame:
    left_on = config.get("left_on")
    right_on = config.get("right_on")
    how = config.get("how", "left")
    suffix = config.get("suffix", "_r")
    if not left_on or not right_on:
        raise ValueError("Join requires left and right key columns")
    if how not in {"left", "right", "inner", "outer"}:
        raise ValueError("Invalid join type")
    return left.merge(right, left_on=left_on, right_on=right_on, how=how, suffixes=("", suffix))


def _apply_groupby(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    group_cols = config.get("group_cols", [])
    specs = config.get("aggs", [])
    if not group_cols:
        raise ValueError("GroupBy requires at least one group column")
    if not specs:
        raise ValueError("GroupBy requires at least one aggregation")
    temp = df.copy()
    grouped = temp.groupby(group_cols, dropna=False, sort=False)
    result = grouped.size().reset_index(name="__row_count__")[group_cols]
    for spec in specs:
        col = spec.get("column")
        agg = spec.get("agg", "count")
        out_name = spec.get("name") or f"{col}_{agg}"
        if agg in {"size", "row_count"}:
            metric = grouped.size().rename(out_name)
            result = result.merge(metric.reset_index(), on=group_cols, how="left")
            continue
        if not col or col not in temp.columns:
            raise ValueError(f"Column not found: {col}")
        raw = grouped[col]
        numeric_col = f"__num_{len(result.columns)}"
        if agg in {"sum", "mean", "median", "min", "max", "std", "var", "p25", "p75"}:
            temp[numeric_col] = _coerce_numeric(temp[col])
            num_grouped = temp.groupby(group_cols, dropna=False, sort=False)[numeric_col]
            if agg == "sum":
                metric = num_grouped.sum(min_count=1).fillna(0)
            elif agg == "mean":
                metric = num_grouped.mean()
            elif agg == "median":
                metric = num_grouped.median()
            elif agg == "min":
                metric = num_grouped.min()
            elif agg == "max":
                metric = num_grouped.max()
            elif agg == "std":
                metric = num_grouped.apply(lambda x: _safe_std(x, ddof=0))
            elif agg == "var":
                metric = num_grouped.apply(lambda x: _safe_var(x, ddof=0))
            elif agg == "p25":
                metric = num_grouped.quantile(0.25)
            else:
                metric = num_grouped.quantile(0.75)
        elif agg == "count":
            metric = raw.count()
        elif agg == "nunique":
            metric = raw.nunique(dropna=True)
        elif agg == "first":
            metric = raw.first()
        elif agg == "last":
            metric = raw.last()
        else:
            raise ValueError(f"Unsupported GroupBy aggregation: {agg}")
        result = result.merge(metric.rename(out_name).reset_index(), on=group_cols, how="left")
    return result


def _apply_named_function(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    fn = config.get("fn")
    cols = config.get("cols", [])
    args = config.get("args", {})
    new_col = (config.get("new_col") or f"{fn}_result").strip()
    out = df.copy()
    no_column_fns = {"excel_pi", "excel_today", "excel_now"}
    data = pd.DataFrame(index=out.index) if fn in no_column_fns and not cols else _selected_frame(out, cols)
    numeric_data = _finite_frame(data)

    if fn == "excel_sum":
        out[new_col] = numeric_data.sum(axis=1)
    elif fn == "excel_product":
        out[new_col] = numeric_data.product(axis=1)
    elif fn == "excel_sumsq":
        out[new_col] = numeric_data.pow(2).sum(axis=1)
    elif fn in {"excel_average", "np_mean"}:
        out[new_col] = numeric_data.mean(axis=1)
    elif fn == "excel_median":
        out[new_col] = numeric_data.median(axis=1)
    elif fn == "excel_min":
        out[new_col] = numeric_data.min(axis=1)
    elif fn == "excel_max":
        out[new_col] = numeric_data.max(axis=1)
    elif fn == "excel_count":
        out[new_col] = data.notna().sum(axis=1)
    elif fn == "excel_counta":
        out[new_col] = data.astype("string").fillna("").ne("").sum(axis=1)
    elif fn == "excel_countblank":
        out[new_col] = data.astype("string").fillna("").eq("").sum(axis=1)
    elif fn == "excel_abs":
        out[new_col] = _num(out, cols[0]).abs()
    elif fn == "excel_round":
        out[new_col] = _num(out, cols[0]).round(_int_arg(args, "decimals", 0))
    elif fn == "excel_roundup":
        decimals = _int_arg(args, "decimals", 0)
        factor = 10 ** decimals
        out[new_col] = np.ceil(_num(out, cols[0]) * factor) / factor
    elif fn == "excel_rounddown":
        decimals = _int_arg(args, "decimals", 0)
        factor = 10 ** decimals
        out[new_col] = np.floor(_num(out, cols[0]) * factor) / factor
    elif fn == "excel_int":
        out[new_col] = np.floor(_num(out, cols[0]))
    elif fn == "excel_trunc":
        decimals = _int_arg(args, "decimals", 0)
        factor = 10 ** decimals
        out[new_col] = np.trunc(_num(out, cols[0]) * factor) / factor
    elif fn == "excel_ceiling":
        significance = _float_arg(args, "significance", 1.0)
        out[new_col] = np.ceil(_num(out, cols[0]) / significance) * significance
    elif fn == "excel_floor":
        significance = _float_arg(args, "significance", 1.0)
        out[new_col] = np.floor(_num(out, cols[0]) / significance) * significance
    elif fn == "excel_even":
        out[new_col] = np.ceil(_num(out, cols[0]) / 2) * 2
    elif fn == "excel_odd":
        s = _num(out, cols[0])
        out[new_col] = np.where((np.ceil(s) % 2) == 0, np.ceil(s) + 1, np.ceil(s))
    elif fn == "excel_mod":
        divisor = _num(out, cols[1]) if len(cols) > 1 else _float_arg(args, "divisor", 1.0)
        out[new_col] = _num(out, cols[0]) % divisor
    elif fn in {"excel_power", "np_power"}:
        power = _num(out, cols[1]) if len(cols) > 1 else _float_arg(args, "power", 2.0)
        with np.errstate(invalid="ignore", over="ignore"):
            out[new_col] = _finite_series(pd.Series(np.power(_num(out, cols[0]), power), index=out.index))
    elif fn in {"excel_sqrt", "np_sqrt"}:
        s = _num(out, cols[0])
        out[new_col] = np.sqrt(s.where(s >= 0))
    elif fn == "excel_exp":
        with np.errstate(over="ignore", invalid="ignore"):
            out[new_col] = _finite_series(pd.Series(np.exp(_num(out, cols[0])), index=out.index))
    elif fn in {"excel_ln", "np_log"}:
        s = _num(out, cols[0])
        out[new_col] = np.log(s.where(s > 0))
    elif fn == "excel_log":
        s = _num(out, cols[0])
        base = _float_arg(args, "base", 10.0)
        out[new_col] = np.log(s.where(s > 0)) / np.log(base)
    elif fn == "excel_log10":
        s = _num(out, cols[0])
        out[new_col] = np.log10(s.where(s > 0))
    elif fn == "excel_sign":
        out[new_col] = np.sign(_num(out, cols[0]))
    elif fn == "excel_pi":
        out[new_col] = math.pi
    elif fn == "excel_radians":
        out[new_col] = np.radians(_num(out, cols[0]))
    elif fn == "excel_degrees":
        out[new_col] = np.degrees(_num(out, cols[0]))
    elif fn == "excel_sin":
        out[new_col] = np.sin(_num(out, cols[0]))
    elif fn == "excel_cos":
        out[new_col] = np.cos(_num(out, cols[0]))
    elif fn == "excel_tan":
        out[new_col] = np.tan(_num(out, cols[0]))
    elif fn == "excel_asin":
        s = _num(out, cols[0])
        out[new_col] = np.arcsin(s.where(s.between(-1, 1)))
    elif fn == "excel_acos":
        s = _num(out, cols[0])
        out[new_col] = np.arccos(s.where(s.between(-1, 1)))
    elif fn == "excel_atan":
        out[new_col] = np.arctan(_num(out, cols[0]))
    elif fn == "excel_atan2":
        if len(cols) < 2:
            raise ValueError("ATAN2 requires two numeric columns")
        out[new_col] = np.arctan2(_num(out, cols[0]), _num(out, cols[1]))
    elif fn == "excel_asinh":
        out[new_col] = np.arcsinh(_num(out, cols[0]))
    elif fn == "excel_acosh":
        s = _num(out, cols[0])
        out[new_col] = np.arccosh(s.where(s >= 1))
    elif fn == "excel_atanh":
        s = _num(out, cols[0])
        out[new_col] = np.arctanh(s.where(s.between(-1, 1, inclusive="neither")))
    elif fn == "excel_sinh":
        out[new_col] = np.sinh(_num(out, cols[0]))
    elif fn == "excel_cosh":
        out[new_col] = np.cosh(_num(out, cols[0]))
    elif fn == "excel_tanh":
        out[new_col] = np.tanh(_num(out, cols[0]))
    elif fn == "excel_cot":
        out[new_col] = _finite_series(1 / np.tan(_num(out, cols[0])))
    elif fn == "excel_coth":
        out[new_col] = _finite_series(1 / np.tanh(_num(out, cols[0])))
    elif fn == "excel_sec":
        out[new_col] = _finite_series(1 / np.cos(_num(out, cols[0])))
    elif fn == "excel_sech":
        out[new_col] = _finite_series(1 / np.cosh(_num(out, cols[0])))
    elif fn == "excel_csc":
        out[new_col] = _finite_series(1 / np.sin(_num(out, cols[0])))
    elif fn == "excel_csch":
        out[new_col] = _finite_series(1 / np.sinh(_num(out, cols[0])))
    elif fn == "excel_gcd":
        out[new_col] = numeric_data.fillna(0).astype(int).abs().apply(lambda r: math.gcd(*r.tolist()), axis=1)
    elif fn == "excel_lcm":
        out[new_col] = numeric_data.fillna(0).astype(int).abs().apply(lambda r: math.lcm(*r.tolist()), axis=1)
    elif fn == "excel_fact":
        out[new_col] = _row_factorial(_num(out, cols[0]))
    elif fn == "excel_len":
        out[new_col] = out[cols[0]].astype(str).str.len()
    elif fn == "excel_upper":
        out[new_col] = out[cols[0]].astype(str).str.upper()
    elif fn == "excel_lower":
        out[new_col] = out[cols[0]].astype(str).str.lower()
    elif fn == "excel_trim":
        out[new_col] = out[cols[0]].astype(str).str.strip()
    elif fn == "excel_proper":
        out[new_col] = out[cols[0]].astype(str).str.title()
    elif fn == "excel_clean":
        out[new_col] = out[cols[0]].astype(str).str.replace(r"[\x00-\x1f\x7f]", "", regex=True)
    elif fn == "excel_exact":
        out[new_col] = out[cols[0]].astype(str).eq(out[cols[1]].astype(str)) if len(cols) > 1 else False
    elif fn == "excel_find":
        text = str(args.get("text", ""))
        out[new_col] = out[cols[0]].astype(str).str.find(text) + 1
    elif fn == "excel_search":
        text = str(args.get("text", "")).lower()
        out[new_col] = out[cols[0]].astype(str).str.lower().str.find(text) + 1
    elif fn == "excel_replace":
        start = max(_int_arg(args, "start", 1) - 1, 0)
        length = _int_arg(args, "length", 1)
        replacement = str(args.get("new", ""))
        out[new_col] = out[cols[0]].astype(str).apply(lambda x: x[:start] + replacement + x[start + length:])
    elif fn == "excel_substitute":
        out[new_col] = out[cols[0]].astype(str).str.replace(str(args.get("old", "")), str(args.get("new", "")), regex=False)
    elif fn == "excel_rept":
        n = _int_arg(args, "n", 1)
        out[new_col] = out[cols[0]].astype(str).str.repeat(n)
    elif fn == "excel_value":
        out[new_col] = _coerce_numeric(out[cols[0]])
    elif fn == "excel_textjoin":
        sep = str(args.get("sep", ""))
        ignore_empty = str(args.get("ignore_empty", "true")).lower() != "false"
        values = data.astype("string").fillna("")
        out[new_col] = values.apply(lambda r: sep.join([v for v in r.tolist() if v or not ignore_empty]), axis=1)
    elif fn == "excel_mid":
        start = max(_int_arg(args, "start", 1) - 1, 0)
        n = _int_arg(args, "n", 1)
        out[new_col] = out[cols[0]].astype(str).str.slice(start, start + n)
    elif fn == "excel_concat":
        out[new_col] = data.astype(str).agg(str(args.get("sep", "")).join, axis=1)
    elif fn == "excel_left":
        out[new_col] = out[cols[0]].astype(str).str[:int(args.get("n", 1))]
    elif fn == "excel_right":
        out[new_col] = out[cols[0]].astype(str).str[-int(args.get("n", 1)):]
    elif fn == "excel_stdev_p":
        out[new_col] = _row_stat(numeric_data, lambda r: _safe_std(r, ddof=0))
    elif fn == "excel_stdev_s":
        out[new_col] = _row_stat(numeric_data, lambda r: _safe_std(r, ddof=1))
    elif fn == "excel_var_p":
        out[new_col] = _row_stat(numeric_data, lambda r: _safe_var(r, ddof=0))
    elif fn == "excel_var_s":
        out[new_col] = _row_stat(numeric_data, lambda r: _safe_var(r, ddof=1))
    elif fn == "excel_percentile_inc":
        out[new_col] = numeric_data.quantile(_float_arg(args, "q", 0.5), axis=1)
    elif fn == "excel_quartile_inc":
        q = _int_arg(args, "quart", 2) / 4
        out[new_col] = numeric_data.quantile(q, axis=1)
    elif fn == "excel_large":
        k = _int_arg(args, "k", 1)
        out[new_col] = numeric_data.apply(lambda r: r.dropna().nlargest(k).iloc[-1] if len(r.dropna()) >= k else np.nan, axis=1)
    elif fn == "excel_small":
        k = _int_arg(args, "k", 1)
        out[new_col] = numeric_data.apply(lambda r: r.dropna().nsmallest(k).iloc[-1] if len(r.dropna()) >= k else np.nan, axis=1)
    elif fn == "excel_rank_eq":
        out[new_col] = _num(out, cols[0]).rank(method="min", ascending=str(args.get("ascending", "false")).lower() == "true")
    elif fn == "excel_devsq":
        out[new_col] = _row_stat(numeric_data, lambda r: _finite_series(r).dropna().sub(_finite_series(r).dropna().mean()).pow(2).sum())
    elif fn == "excel_geomean":
        out[new_col] = numeric_data.apply(lambda r: np.exp(np.log(r[(r > 0) & r.notna()]).mean()) if len(r[(r > 0) & r.notna()]) else np.nan, axis=1)
    elif fn == "excel_harmean":
        out[new_col] = numeric_data.apply(lambda r: len(r[(r > 0) & r.notna()]) / (1 / r[(r > 0) & r.notna()]).sum() if len(r[(r > 0) & r.notna()]) else np.nan, axis=1)
    elif fn == "excel_correl":
        out[new_col] = numeric_data[cols[0]].corr(numeric_data[cols[1]]) if len(cols) > 1 else np.nan
    elif fn == "excel_covariance_p":
        out[new_col] = numeric_data[cols[0]].cov(numeric_data[cols[1]], ddof=0) if len(cols) > 1 else np.nan
    elif fn == "excel_skew":
        out[new_col] = _row_stat(numeric_data, _safe_skew, default=0.0)
    elif fn == "excel_kurt":
        out[new_col] = _row_stat(numeric_data, _safe_kurt, default=0.0)
    elif fn == "excel_today":
        out[new_col] = pd.Timestamp.today().normalize()
    elif fn == "excel_now":
        out[new_col] = pd.Timestamp.now()
    elif fn == "excel_year":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.year
    elif fn == "excel_month":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.month
    elif fn == "excel_day":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.day
    elif fn == "excel_hour":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.hour
    elif fn == "excel_minute":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.minute
    elif fn == "excel_second":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.second
    elif fn == "excel_weekday":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.weekday + 1
    elif fn == "excel_weeknum":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.isocalendar().week.astype("Int64")
    elif fn == "excel_days":
        if len(cols) < 2:
            raise ValueError("DAYS requires two date columns")
        out[new_col] = (pd.to_datetime(out[cols[0]], errors="coerce") - pd.to_datetime(out[cols[1]], errors="coerce")).dt.days
    elif fn == "excel_datedif":
        if len(cols) < 2:
            raise ValueError("DATEDIF requires two date columns")
        start = pd.to_datetime(out[cols[0]], errors="coerce")
        end = pd.to_datetime(out[cols[1]], errors="coerce")
        unit = str(args.get("unit", "D")).upper()
        days = (end - start).dt.days
        out[new_col] = np.floor(days / 365.25) if unit == "Y" else np.floor(days / 30.4375) if unit == "M" else days
    elif fn == "excel_and":
        out[new_col] = data.apply(lambda r: all(_bool_series(r)), axis=1)
    elif fn == "excel_or":
        out[new_col] = data.apply(lambda r: any(_bool_series(r)), axis=1)
    elif fn == "excel_not":
        out[new_col] = ~_bool_series(out[cols[0]])
    elif fn == "excel_if":
        condition = _bool_series(out[cols[0]])
        out[new_col] = np.where(condition, args.get("true", "True"), args.get("false", "False"))
    elif fn == "excel_iferror":
        fallback = args.get("fallback", "")
        out[new_col] = out[cols[0]].replace([np.inf, -np.inf], np.nan).fillna(fallback)
    elif fn == "excel_isblank":
        out[new_col] = out[cols[0]].astype("string").fillna("").eq("")
    elif fn == "excel_isnumber":
        out[new_col] = _num(out, cols[0]).notna()
    elif fn == "excel_iseven":
        out[new_col] = (_num(out, cols[0]) % 2).eq(0)
    elif fn == "excel_isodd":
        out[new_col] = (_num(out, cols[0]) % 2).eq(1)
    elif fn == "pd_fillna":
        out[new_col] = out[cols[0]].replace("", np.nan).fillna(args.get("value", ""))
    elif fn == "pd_replace":
        out[new_col] = out[cols[0]].astype(str).str.replace(str(args.get("old", "")), str(args.get("new", "")), regex=False)
    elif fn == "pd_contains":
        out[new_col] = out[cols[0]].astype(str).str.contains(str(args.get("text", "")), case=False, na=False)
    elif fn == "pd_to_numeric":
        out[new_col] = _coerce_numeric(out[cols[0]])
    elif fn == "pd_to_datetime":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce")
    elif fn == "pd_rank":
        out[new_col] = _num(out, cols[0]).rank(method="dense", ascending=str(args.get("ascending", "true")).lower() != "false")
    elif fn == "pd_diff":
        out[new_col] = _num(out, cols[0]).diff(int(args.get("periods", 1)))
    elif fn == "pd_pct_change":
        out[new_col] = _num(out, cols[0]).pct_change(int(args.get("periods", 1)))
    elif fn == "pd_rolling_mean":
        out[new_col] = _num(out, cols[0]).rolling(int(args.get("window", 3)), min_periods=1).mean()
    elif fn == "pd_year":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.year
    elif fn == "pd_month":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.month
    elif fn == "pd_day":
        out[new_col] = pd.to_datetime(out[cols[0]], errors="coerce").dt.day
    elif fn == "np_std":
        out[new_col] = _row_stat(numeric_data, lambda r: _safe_std(r, ddof=0))
    elif fn == "np_percentile":
        out[new_col] = numeric_data.quantile(float(args.get("q", 0.5)), axis=1)
    elif fn == "np_sqrt":
        s = _num(out, cols[0])
        out[new_col] = np.sqrt(s.where(s >= 0))
    elif fn == "np_log":
        s = _num(out, cols[0])
        out[new_col] = np.log(s.where(s > 0))
    elif fn == "np_power":
        with np.errstate(invalid="ignore", over="ignore"):
            out[new_col] = _finite_series(pd.Series(np.power(_num(out, cols[0]), float(args.get("power", 2))), index=out.index))
    elif fn == "np_clip":
        out[new_col] = np.clip(_num(out, cols[0]), float(args.get("min", 0)), float(args.get("max", 1)))
    elif fn == "np_zscore":
        s = _num(out, cols[0])
        std = _safe_std(s, ddof=0)
        out[new_col] = 0 if std == 0 or pd.isna(std) else (s - s.mean()) / std
    elif fn == "np_where":
        s = _num(out, cols[0])
        out[new_col] = np.where(s > float(args.get("threshold", 0)), args.get("true", "True"), args.get("false", "False"))
    else:
        raise ValueError(f"Unsupported function: {fn}")
    return out
