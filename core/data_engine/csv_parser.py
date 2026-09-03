"""
Smart CSV column detection and dataset validation.

Handles the heterogeneity of NSE historical data formats by using fuzzy
matching to map arbitrary column names to our canonical schema.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import StringIO
from typing import IO

import pandas as pd

from core.data_engine.schema import (
    CANONICAL_COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    DatasetReport,
)

# ── Column name mappings ───────────────────────────────────────────────
# Maps known variations of column names to canonical field names.
# Keys are lowercase, stripped of underscores/spaces/hyphens.

_COLUMN_ALIASES: dict[str, list[str]] = {
    "timestamp": [
        "timestamp", "date", "trading_date", "trade_date", "dt",
        "datetime", "time", "tradingdate",
    ],
    "underlying": [
        "underlying", "symbol", "ticker", "instrument", "underlying_value",
        "index", "scrip",
    ],
    "underlying_close": [
        "underlying_close", "underlying_value", "spot", "spot_close",
        "spot_price", "index_close", "underlying_last",
    ],
    "expiry": [
        "expiry", "expiry_date", "expiry_dt", "expirydate", "expdt",
        "exp_date", "expdate",
    ],
    "strike": [
        "strike", "strike_price", "strikeprice", "strike_pr", "strikepr",
        "exercise_price",
    ],
    "option_type": [
        "option_type", "optiontype", "option_typ", "type", "opt_type",
        "call_put", "cp", "ce_pe", "optiontypce_pe",
    ],
    "open": ["open", "open_price", "openprice"],
    "high": ["high", "high_price", "highprice"],
    "low": ["low", "low_price", "lowprice"],
    "close": [
        "close", "close_price", "closeprice", "settle_price", "settle_pr",
        "settleprice", "ltp", "last", "last_price", "lastprice",
    ],
    "volume": [
        "volume", "vol", "traded_qty", "tradedqty", "no_of_contracts",
        "contracts", "traded_volume",
    ],
    "oi": [
        "oi", "open_interest", "openinterest", "open_int", "openint",
        "oi_contracts",
    ],
    "bid": ["bid", "bid_price", "bidprice", "best_bid", "bid1"],
    "ask": [
        "ask", "ask_price", "askprice", "best_ask", "ask1",
        "offer", "offer_price",
    ],
}


def _normalize_col_name(name: str) -> str:
    """Normalize a column name for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _detect_column_mapping(columns: list[str]) -> dict[str, str]:
    """
    Given raw CSV column names, detect which canonical field each maps to.

    Returns:
        dict mapping canonical_name → original_column_name
    """
    mapping: dict[str, str] = {}
    used_columns: set[str] = set()

    for canonical, aliases in _COLUMN_ALIASES.items():
        normalized_aliases = {_normalize_col_name(a) for a in aliases}
        for col in columns:
            if col in used_columns:
                continue
            if _normalize_col_name(col) in normalized_aliases:
                mapping[canonical] = col
                used_columns.add(col)
                break

    return mapping


# ── Date parsing ───────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%d-%b-%Y",      # 01-Jan-2025
    "%d-%B-%Y",      # 01-January-2025
    "%Y-%m-%d",      # 2025-01-01
    "%d/%m/%Y",      # 01/01/2025
    "%m/%d/%Y",      # 01/01/2025 (US)
    "%d-%m-%Y",      # 01-01-2025
    "%Y%m%d",        # 20250101
    "%d %b %Y",      # 01 Jan 2025
    "%d-%b-%y",      # 01-Jan-25
]


def _parse_date_column(series: pd.Series) -> pd.Series:
    """Parse a date column trying multiple formats."""
    # First try pandas auto-detection
    try:
        return pd.to_datetime(series, dayfirst=True)
    except Exception:
        pass

    # Try specific formats
    for fmt in _DATE_FORMATS:
        try:
            return pd.to_datetime(series, format=fmt)
        except Exception:
            continue

    # Last resort: coerce
    return pd.to_datetime(series, errors="coerce", dayfirst=True)


# ── Option type detection ──────────────────────────────────────────────

def _normalize_option_type(series: pd.Series) -> pd.Series:
    """Normalize option type values to 'CE' or 'PE'."""
    mapping = {
        "ce": "CE", "call": "CE", "c": "CE", "call european": "CE",
        "pe": "PE", "put": "PE", "p": "PE", "put european": "PE",
    }
    return series.str.strip().str.lower().map(mapping).fillna(series)


# ── Main parsing function ─────────────────────────────────────────────

def parse_csv(
    file: IO | str | pd.DataFrame,
    underlying_name: str = "NIFTY",
    underlying_close_override: pd.Series | None = None,
) -> tuple[pd.DataFrame, DatasetReport]:
    """
    Parse a CSV file (or DataFrame) into canonical format.

    Args:
        file: File-like object, file path string, or pre-loaded DataFrame
        underlying_name: Name of the underlying instrument
        underlying_close_override: Optional series of underlying close prices
            indexed by date, used when the CSV doesn't contain underlying prices

    Returns:
        Tuple of (normalized DataFrame, DatasetReport)
    """
    # Load raw data
    if isinstance(file, pd.DataFrame):
        raw_df = file.copy()
    elif isinstance(file, str) and "\n" in file:
        raw_df = pd.read_csv(StringIO(file))
    else:
        raw_df = pd.read_csv(file)

    raw_columns = list(raw_df.columns)
    warnings: list[str] = []

    # Detect column mapping
    col_map = _detect_column_mapping(raw_columns)

    # Check required fields
    missing_required = []
    for req in REQUIRED_COLUMNS:
        if req not in col_map:
            # Special handling: underlying and underlying_close can be inferred
            if req == "underlying":
                continue  # We'll fill it with underlying_name
            if req == "underlying_close" and underlying_close_override is not None:
                continue
            missing_required.append(req)

    missing_optional = [opt for opt in OPTIONAL_COLUMNS if opt not in col_map]

    if missing_optional:
        if "bid" in missing_optional and "ask" in missing_optional:
            warnings.append("No bid/ask data — slippage will be estimated")
        if "volume" in missing_optional:
            warnings.append("No volume data — liquidity cannot be assessed")
        if "oi" in missing_optional:
            warnings.append("No open interest data")

    # Build normalized DataFrame
    df = pd.DataFrame()

    # Timestamp
    if "timestamp" in col_map:
        df["timestamp"] = _parse_date_column(raw_df[col_map["timestamp"]])
    else:
        missing_required.append("timestamp")

    # Underlying
    if "underlying" in col_map:
        df["underlying"] = raw_df[col_map["underlying"]].astype(str).str.upper()
    else:
        df["underlying"] = underlying_name

    # Expiry
    if "expiry" in col_map:
        df["expiry"] = _parse_date_column(raw_df[col_map["expiry"]])

    # Strike
    if "strike" in col_map:
        df["strike"] = pd.to_numeric(raw_df[col_map["strike"]], errors="coerce")

    # Option type
    if "option_type" in col_map:
        df["option_type"] = _normalize_option_type(
            raw_df[col_map["option_type"]].astype(str)
        )
    else:
        # Try to detect from filename or other hints
        pass

    # Price columns
    for price_col in ["open", "high", "low", "close"]:
        if price_col in col_map:
            df[price_col] = pd.to_numeric(
                raw_df[col_map[price_col]], errors="coerce"
            )

    # Underlying close
    if "underlying_close" in col_map:
        df["underlying_close"] = pd.to_numeric(
            raw_df[col_map["underlying_close"]], errors="coerce"
        )
    elif underlying_close_override is not None:
        # Merge underlying close by date
        if "timestamp" in df.columns:
            date_index = df["timestamp"].dt.date
            df["underlying_close"] = date_index.map(
                underlying_close_override.to_dict()
            ).astype(float)
    else:
        df["underlying_close"] = float("nan")

    # Optional columns
    for opt_col in OPTIONAL_COLUMNS:
        if opt_col in col_map:
            df[opt_col] = pd.to_numeric(
                raw_df[col_map[opt_col]], errors="coerce"
            )
        else:
            df[opt_col] = float("nan")

    # ── Post-processing ─────────────────────────────────────────────

    # Drop rows with NaN in critical columns
    critical = ["timestamp", "strike", "close"]
    available_critical = [c for c in critical if c in df.columns]
    if available_critical:
        before = len(df)
        df = df.dropna(subset=available_critical)
        dropped = before - len(df)
        if dropped > 0:
            warnings.append(f"{dropped} rows dropped due to missing critical data")

    # Sort by timestamp and strike
    sort_cols = [c for c in ["timestamp", "strike", "option_type"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Check for intraday vs EOD
    if "timestamp" in df.columns and not df.empty:
        times = df["timestamp"].dt.time.unique()
        if len(times) <= 1:
            warnings.append("EOD data only — intraday execution cannot be validated")

    # ── Build report ────────────────────────────────────────────────

    date_range = None
    trading_days = 0
    expiry_count = 0
    contract_count = 0

    if "timestamp" in df.columns and not df.empty:
        dates = df["timestamp"].dt.date
        date_range = (dates.min(), dates.max())
        trading_days = dates.nunique()

    if "expiry" in df.columns and not df.empty:
        expiry_count = df["expiry"].dt.date.nunique()

    if "strike" in df.columns and "option_type" in df.columns and not df.empty:
        contract_count = df.groupby(
            ["strike", "option_type", "expiry"]
        ).ngroups if "expiry" in df.columns else df.groupby(
            ["strike", "option_type"]
        ).ngroups

    report = DatasetReport(
        detected_fields={k: v for k, v in col_map.items()},
        missing_required=missing_required,
        missing_optional=missing_optional,
        date_range=date_range,
        trading_days=trading_days,
        expiry_count=expiry_count,
        contract_count=contract_count,
        row_count=len(df),
        warnings=warnings,
    )

    return df, report


def parse_separate_ce_pe(
    ce_file: IO | str,
    pe_file: IO | str,
    underlying_name: str = "NIFTY",
) -> tuple[pd.DataFrame, DatasetReport]:
    """
    Parse separate CE and PE CSV files and combine them.

    Some data providers give CE and PE data in separate files.
    This function handles that by parsing each, tagging option_type,
    and concatenating.
    """
    ce_df, ce_report = parse_csv(ce_file, underlying_name)
    pe_df, pe_report = parse_csv(pe_file, underlying_name)

    # Force option types if not detected
    if "option_type" not in ce_report.detected_fields:
        ce_df["option_type"] = "CE"
    if "option_type" not in pe_report.detected_fields:
        pe_df["option_type"] = "PE"

    combined = pd.concat([ce_df, pe_df], ignore_index=True)
    sort_cols = [c for c in ["timestamp", "strike", "option_type"]
                 if c in combined.columns]
    if sort_cols:
        combined = combined.sort_values(sort_cols).reset_index(drop=True)

    # Merge reports
    all_detected = {**ce_report.detected_fields, **pe_report.detected_fields}
    all_warnings = list(set(ce_report.warnings + pe_report.warnings))

    date_range = None
    if ce_report.date_range and pe_report.date_range:
        date_range = (
            min(ce_report.date_range[0], pe_report.date_range[0]),
            max(ce_report.date_range[1], pe_report.date_range[1]),
        )
    elif ce_report.date_range:
        date_range = ce_report.date_range
    elif pe_report.date_range:
        date_range = pe_report.date_range

    combined_report = DatasetReport(
        detected_fields=all_detected,
        missing_required=list(
            set(ce_report.missing_required) & set(pe_report.missing_required)
        ),
        missing_optional=list(
            set(ce_report.missing_optional) & set(pe_report.missing_optional)
        ),
        date_range=date_range,
        trading_days=ce_report.trading_days + pe_report.trading_days,
        expiry_count=max(ce_report.expiry_count, pe_report.expiry_count),
        contract_count=ce_report.contract_count + pe_report.contract_count,
        row_count=len(combined),
        warnings=all_warnings,
    )

    return combined, combined_report
