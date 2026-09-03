"""Tests for CSV parser column detection and date parsing."""

import os
from datetime import date

import pytest
import pandas as pd

from core.data_engine.csv_parser import parse_csv, parse_separate_ce_pe

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CSV = os.path.join(FIXTURES_DIR, "sample_nifty.csv")


class TestColumnDetection:
    """Test that various column naming schemes are correctly detected."""

    def test_nse_standard_columns(self):
        """Standard NSE column names should be detected."""
        df, report = parse_csv(SAMPLE_CSV)
        assert report.is_valid, f"Missing required: {report.missing_required}"
        assert "timestamp" in report.detected_fields
        assert "strike" in report.detected_fields
        assert "option_type" in report.detected_fields
        assert "close" in report.detected_fields

    def test_alternative_column_names(self):
        """Alternative column names should be mapped correctly."""
        csv_data = """trading_date,expiry_dt,strike_pr,option_typ,ltp,underlying_value
02-Jun-2025,05-Jun-2025,25000,CE,150.5,25000
02-Jun-2025,05-Jun-2025,25000,PE,145.0,25000
"""
        df, report = parse_csv(csv_data)
        assert "timestamp" in report.detected_fields
        assert "expiry" in report.detected_fields
        assert "strike" in report.detected_fields
        assert "option_type" in report.detected_fields
        assert "close" in report.detected_fields

    def test_missing_required_fields(self):
        """Missing required fields should be reported."""
        csv_data = """col_a,col_b
1,2
3,4
"""
        df, report = parse_csv(csv_data)
        assert not report.is_valid
        assert len(report.missing_required) > 0


class TestDateParsing:
    """Test various date format detection."""

    def test_dd_mon_yyyy(self):
        """DD-Mon-YYYY format (common in NSE data)."""
        df, report = parse_csv(SAMPLE_CSV)
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_yyyy_mm_dd(self):
        """YYYY-MM-DD format."""
        csv_data = """Date,Strike Price,Option Type,Close,Expiry Date,Underlying Value
2025-06-02,25000,CE,150.5,2025-06-05,25000
2025-06-02,25000,PE,145.0,2025-06-05,25000
"""
        df, report = parse_csv(csv_data)
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


class TestDatasetReport:
    """Test dataset report generation."""

    def test_report_statistics(self):
        """Report should contain accurate statistics."""
        df, report = parse_csv(SAMPLE_CSV)
        assert report.trading_days > 0
        assert report.expiry_count > 0
        assert report.contract_count > 0
        assert report.row_count == len(df)

    def test_date_range_detection(self):
        """Date range should be correctly detected."""
        df, report = parse_csv(SAMPLE_CSV)
        assert report.date_range is not None
        start, end = report.date_range
        assert start < end

    def test_eod_warning(self):
        """EOD-only data should generate a warning."""
        df, report = parse_csv(SAMPLE_CSV)
        eod_warnings = [w for w in report.warnings if "EOD" in w]
        assert len(eod_warnings) > 0, "Should warn about EOD data"

    def test_optional_field_warnings(self):
        """Missing bid/ask should generate a warning."""
        df, report = parse_csv(SAMPLE_CSV)
        bid_ask_warnings = [w for w in report.warnings if "bid/ask" in w.lower()]
        assert len(bid_ask_warnings) > 0, "Should warn about missing bid/ask"


class TestOptionTypeNormalization:
    """Test option type value normalization."""

    def test_ce_pe_uppercase(self):
        """CE and PE should be normalized to uppercase."""
        df, report = parse_csv(SAMPLE_CSV)
        unique_types = df["option_type"].unique()
        assert set(unique_types) == {"CE", "PE"}
