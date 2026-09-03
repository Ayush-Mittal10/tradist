"""
Data normalizer: transforms parsed DataFrames into canonical format
and persists them as Parquet files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.data_engine.schema import CANONICAL_COLUMNS, REQUIRED_COLUMNS


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a parsed DataFrame conforms to the canonical schema.

    - Enforces column order
    - Casts types
    - Fills missing optional columns with NaN
    - Validates required columns are present
    """
    # Ensure all canonical columns exist
    for col, dtype in CANONICAL_COLUMNS.items():
        if col not in df.columns:
            if col in REQUIRED_COLUMNS:
                raise ValueError(f"Required column '{col}' is missing from data")
            df[col] = float("nan")

    # Enforce column order
    df = df[[c for c in CANONICAL_COLUMNS if c in df.columns]]

    # Cast types
    for col, dtype in CANONICAL_COLUMNS.items():
        if col not in df.columns:
            continue
        if dtype == "datetime64[ns]":
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col], errors="coerce")
        elif dtype == "float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        elif dtype == "str":
            df[col] = df[col].astype(str)

    return df


def save_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    """Save a normalized DataFrame as a Parquet file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")
    return path


def load_parquet(path: str | Path) -> pd.DataFrame:
    """Load a previously saved Parquet dataset."""
    return pd.read_parquet(path, engine="pyarrow")
