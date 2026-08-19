# ================================================================
# engine/datastore.py — DataStore
# Arrow cache | Index | Column typing | Thread-safe
# ================================================================

import os, gc, time, logging, threading, tempfile, shutil
from typing import Optional, Dict, List, Tuple, Any

import pandas as pd
import numpy as np

logger = logging.getLogger("jet.datastore")


def safe_fill_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if isinstance(s, pd.DataFrame):
            continue
        try:
            if pd.api.types.is_numeric_dtype(s):
                out[col] = s.replace([np.inf, -np.inf], np.nan).fillna(0)
            elif pd.api.types.is_bool_dtype(s):
                out[col] = s.fillna(False)
            elif pd.api.types.is_datetime64_any_dtype(s):
                out[col] = s
            else:
                out[col] = s.astype("object").where(pd.notna(s), "")
        except Exception:
            logger.warning(f"Kolon fillna atlandi: {col}", exc_info=True)
    return out

# ─────────────────────────────────────────────────────────────
# FileEntry: tek dosyanın meta + DataFrame'i
# ─────────────────────────────────────────────────────────────

class FileEntry:
    __slots__ = [
        'name', 'filepath', 'df', 'rows', 'col_names',
        'sheet_names', 'selected_sheet',
        'col_types',       # {col: 'text'|'numeric'|'date'}
        'index_cache',     # {col: sorted unique values}
        'parquet_path',    # hızlı yeniden okuma için önbellek
        'load_options',
        'loaded_at', 'file_size',
    ]

    def __init__(self, name: str, filepath: str):
        self.name            = name
        self.filepath        = filepath
        self.df: Optional[pd.DataFrame] = None
        self.rows            = 0
        self.col_names: List[str] = []
        self.sheet_names: List[str] = []
        self.selected_sheet  = ''
        self.col_types: Dict[str, str] = {}
        self.index_cache: Dict[str, List] = {}
        self.parquet_path: Optional[str] = None
        self.load_options: Dict[str, Any] = {}
        self.loaded_at       = time.time()
        self.file_size       = os.path.getsize(filepath) if os.path.exists(filepath) and not filepath.startswith('virtual://') else 0

    def _series(self, col: str) -> pd.Series:
        data = self.df[col]
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]
        return data

    def infer_types(self):
        if self.df is None:
            return
        types = {}
        for col in self.df.columns:
            sample = self._series(col).dropna().head(500)
            if sample.empty:
                types[col] = 'text'
                continue
            num = pd.to_numeric(
                sample.astype(str).str.replace(',', '.', regex=False),
                errors='coerce'
            )
            if num.notna().sum() / len(sample) > 0.85:
                types[col] = 'numeric'
                continue
            try:
                parsed = pd.to_datetime(sample, errors='coerce', infer_datetime_format=True)
                if parsed.notna().sum() / len(sample) > 0.70:
                    types[col] = 'date'
                    continue
            except Exception:
                pass
            types[col] = 'text'
        self.col_types = types

    def build_index(self, max_unique: int = 50_000):
        if self.df is None:
            return
        cache = {}
        for col in self.df.columns:
            s = self._series(col)
            n_unique = s.nunique()
            if n_unique <= max_unique:
                vals = sorted(s.dropna().unique().tolist())
                cache[col] = vals[:max_unique]
        self.index_cache = cache

    def cache_to_parquet(self, cache_dir: str):
        if self.df is None:
            return
        try:
            path = os.path.join(cache_dir, f"{self.name.replace('/', '_').replace('\\', '_')}.parquet")
            self.df.to_parquet(path, index=False, compression='snappy')
            self.parquet_path = path
        except Exception as e:
            logger.warning(f"Parquet cache hatası: {e}")

    def to_info(self) -> dict:
        return {
            'name':           self.name,
            'filepath':       self.filepath,
            'rows':           self.rows,
            'cols':           len(self.col_names),
            'col_names':      self.col_names,
            'sheet_names':    self.sheet_names,
            'selected_sheet': self.selected_sheet,
            'col_types':      self.col_types,
            'file_size_bytes': self.file_size,
            'file_size_mb':   round(self.file_size / 1024 / 1024, 2),
            'loaded_at':      self.loaded_at
        }


# ─────────────────────────────────────────────────────────────
# DataStore: tüm dosyaların thread-safe yöneticisi
# ─────────────────────────────────────────────────────────────

class DataStore:
    def __init__(self):
        self._lock    = threading.RLock()
        self._entries: Dict[str, FileEntry] = {}
        self._order:  List[str] = []
        self._cache_dir = tempfile.mkdtemp(prefix='jet_cache_')
        logger.info(f"DataStore cache dir: {self._cache_dir}")

    def add_entry(self, entry: FileEntry):
        with self._lock:
            if entry.name in self._entries:
                self._order.remove(entry.name)
            self._entries[entry.name] = entry
            self._order.append(entry.name)

    def remove_entry(self, name: str):
        with self._lock:
            if name in self._entries:
                del self._entries[name]
                self._order.remove(name)

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._order.clear()
        gc.collect()

    def get_entry(self, name: str) -> Optional[FileEntry]:
        with self._lock:
            return self._entries.get(name)

    def get_df(self, name: str) -> Optional[pd.DataFrame]:
        with self._lock:
            entry = self._entries.get(name)
            return entry.df if entry else None

    def columns_for(self, name: str) -> List[str]:
        d = self.get_df(name)
        return list(d.columns) if d is not None else []

    def row_count_for(self, name: str) -> int:
        d = self.get_df(name)
        return len(d) if d is not None else 0

    def update_entry_df(self, name: str, df: pd.DataFrame):
        with self._lock:
            entry = self._entries.get(name)
            if not entry:
                raise ValueError(f"{name} bulunamadi")
            entry.df = safe_fill_dataframe(df)
            entry.rows = len(entry.df)
            entry.col_names = list(entry.df.columns)
            entry.infer_types()
            entry.build_index(max_unique=5_000)

    def all_entries(self) -> List[FileEntry]:
        with self._lock:
            return [self._entries[n] for n in self._order if n in self._entries]

    def info_list(self) -> List[dict]:
        with self._lock:
            return [self._entries[n].to_info() for n in self._order if n in self._entries]

    def cache_entry(self, name: str):
        entry = self.get_entry(name)
        if entry:
            entry.cache_to_parquet(self._cache_dir)

    def cleanup(self):
        try:
            shutil.rmtree(self._cache_dir, ignore_errors=True)
        except Exception:
            pass

    def query(self, file_name: str, page: int = 0, per: int = 100,
              filters: Optional[Dict[str, str]] = None,
              sort_col: Optional[str] = None,
              sort_asc: bool = True) -> Tuple[List[str], List[dict], int]:
        df = self.get_df(file_name)
        if df is None:
            return [], [], 0

        if filters:
            import re as _re
            mask = pd.Series(True, index=df.index)
            for col, val in filters.items():
                if col in df.columns and val:
                    try:
                        col_data = df[col]
                        if isinstance(col_data, pd.DataFrame):
                            col_data = col_data.iloc[:, 0]
                        mask &= col_data.astype(str).str.contains(
                            _re.escape(str(val)), case=False, na=False)
                    except Exception:
                        pass
            df = df.loc[mask]

        if sort_col and sort_col in df.columns:
            try:
                df = df.sort_values(sort_col, ascending=sort_asc)
            except ValueError:
                tmp_sort_col = "__jet_sort_key__"
                sort_data = df[sort_col]
                if isinstance(sort_data, pd.DataFrame):
                    sort_data = sort_data.iloc[:, 0]
                df = df.assign(**{tmp_sort_col: sort_data}).sort_values(tmp_sort_col, ascending=sort_asc).drop(columns=[tmp_sort_col])

        total = len(df)
        chunk = df.iloc[page * per: (page + 1) * per]

        cols = list(df.columns)
        rows = []
        for row in chunk.itertuples(index=False):
            rows.append({c: _safe(v) for c, v in zip(cols, row)})

        return cols, rows, total

    def __del__(self):
        self.cleanup()

def _safe(v) -> Any:
    if isinstance(v, (np.integer,)):  return int(v)
    if isinstance(v, (np.floating,)): return float(v)
    if isinstance(v, (np.bool_,)):    return bool(v)
    try:
        if pd.isna(v): return ''
    except Exception:
        pass
    return str(v) if not isinstance(v, str) else v
