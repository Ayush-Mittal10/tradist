"""Tests for data normalizer."""

import os

import pytest
import pandas as pd

from core.data_engine.csv_parser import parse_csv
from core.data_engine.normalizer import normalize, save_parquet, load_parquet
from core.data_engine.schema import CANONICAL_COLUMNS

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CSV = os.path.join(FIXTURES_DIR, "sample_nifty.csv")


class TestNormalize:
    """Test DataFrame normalization."""

    def test_column_order(self):
        """Normalized DF should have canonical column order."""
        df, _ = parse_csv(SAMPLE_CSV)
        normalized = normalize(df)
        expected_cols = [c for c in CANONICAL_COLUMNS if c in normalized.columns]
        assert list(normalized.columns) == expected_cols

    def test_types(self):
        """Columns should have correct types after normalization."""
        df, _ = parse_csv(SAMPLE_CSV)
        normalized = normalize(df)
        assert pd.api.types.is_datetime64_any_dtype(normalized["timestamp"])
        assert pd.api.types.is_float_dtype(normalized["strike"])
        assert pd.api.types.is_float_dtype(normalized["close"])

    def test_no_nans_in_required(self):
        """Required columns should not have NaN values after normalization."""
        df, _ = parse_csv(SAMPLE_CSV)
        normalized = normalize(df)
        for col in ["timestamp", "strike", "close"]:
            assert not normalized[col].isna().any(), f"NaN found in {col}"


class TestParquetRoundTrip:
    """Test Parquet save/load."""

    def test_round_trip(self, tmp_path):
        """Data should survive a Parquet round-trip."""
        df, _ = parse_csv(SAMPLE_CSV)
        normalized = normalize(df)

        path = tmp_path / "test.parquet"
        save_parquet(normalized, path)
        loaded = load_parquet(path)

        assert len(loaded) == len(normalized)
        assert list(loaded.columns) == list(normalized.columns)
        pd.testing.assert_frame_equal(normalized, loaded, check_dtype=False)
