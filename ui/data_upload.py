"""
CSV upload and dataset validation UI component.

Renders the data upload interface with smart column detection,
field validation display, and dataset statistics.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from core.data_engine.csv_parser import parse_csv, parse_separate_ce_pe
from core.data_engine.normalizer import normalize
from core.data_engine.schema import REQUIRED_COLUMNS, OPTIONAL_COLUMNS, DatasetReport


def render_data_upload() -> tuple[pd.DataFrame | None, DatasetReport | None]:
    """
    Render the data upload section.

    Returns:
        Tuple of (normalized DataFrame, DatasetReport) if data is loaded,
        or (None, None) if no data yet.
    """
    st.markdown('<div class="section-header">📁 Historical Data</div>', unsafe_allow_html=True)

    upload_mode = st.radio(
        "Upload mode",
        ["Combined CSV (CE + PE)", "Separate CE and PE files"],
        horizontal=True,
        label_visibility="collapsed",
    )

    df = None
    report = None

    if upload_mode == "Combined CSV (CE + PE)":
        uploaded = st.file_uploader(
            "Upload NIFTY options data (CSV)",
            type=["csv"],
            key="combined_csv",
            help="CSV with columns for date, strike, option type (CE/PE), and prices",
        )
        if uploaded is not None:
            upload_id = f"comb_{uploaded.name}_{uploaded.size}"
            if st.session_state.get("_last_upload_id") == upload_id and "dataset" in st.session_state:
                df = st.session_state["dataset"]
                report = st.session_state.get("dataset_report")
            else:
                with st.spinner("Parsing and validating..."):
                    try:
                        df, report = parse_csv(uploaded)
                        if report.is_valid and df is not None:
                            df = normalize(df)
                            st.session_state["dataset"] = df
                            st.session_state["dataset_report"] = report
                            st.session_state["_last_upload_id"] = upload_id
                    except Exception as e:
                        st.error(f"Error parsing uploaded file: {e}")
                        return None, None

    else:
        col1, col2 = st.columns(2)
        with col1:
            ce_file = st.file_uploader(
                "📈 Upload CE data",
                type=["csv"],
                key="ce_csv",
            )
        with col2:
            pe_file = st.file_uploader(
                "📉 Upload PE data",
                type=["csv"],
                key="pe_csv",
            )
        if ce_file is not None and pe_file is not None:
            upload_id = f"sep_{ce_file.name}_{ce_file.size}_{pe_file.name}_{pe_file.size}"
            if st.session_state.get("_last_upload_id") == upload_id and "dataset" in st.session_state:
                df = st.session_state["dataset"]
                report = st.session_state.get("dataset_report")
            else:
                with st.spinner("Parsing and validating..."):
                    try:
                        df, report = parse_separate_ce_pe(ce_file, pe_file)
                        if report.is_valid and df is not None:
                            df = normalize(df)
                            st.session_state["dataset"] = df
                            st.session_state["dataset_report"] = report
                            st.session_state["_last_upload_id"] = upload_id
                    except Exception as e:
                        st.error(f"Error parsing CE/PE files: {e}")
                        return None, None

    # Show validation results
    if report is not None:
        _render_validation_report(report)

    # Check session state for previously loaded data
    if df is None and "dataset" in st.session_state:
        df = st.session_state["dataset"]
        report = st.session_state.get("dataset_report")

    return df, report


def _render_validation_report(report: DatasetReport):
    """Render the dataset validation report with detected/missing fields."""

    st.markdown("---")
    st.markdown("#### 🔍 Dataset Validation")

    # Field detection status
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Required Fields**")
        for field in REQUIRED_COLUMNS:
            if field in report.detected_fields:
                original = report.detected_fields[field]
                st.markdown(
                    f'<div class="field-check detected">'
                    f'<span class="icon">✅</span>'
                    f'{field} <span style="color: #555570; margin-left: 0.5rem">← {original}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="field-check missing">'
                    f'<span class="icon">❌</span>'
                    f'{field} — <b>not found</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with col2:
        st.markdown("**Optional Fields**")
        for field in OPTIONAL_COLUMNS:
            if field in report.detected_fields:
                original = report.detected_fields[field]
                st.markdown(
                    f'<div class="field-check detected">'
                    f'<span class="icon">✅</span>'
                    f'{field} <span style="color: #555570; margin-left: 0.5rem">← {original}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="field-check missing">'
                    f'<span class="icon">⚠️</span>'
                    f'{field} — not available'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Dataset statistics
    if report.date_range:
        st.markdown("---")
        start, end = report.date_range
        stats_html = f"""
        <div class="dataset-stats">
            <div class="stat">
                <span class="stat-label">Coverage</span>
                <span class="stat-value">{start.strftime('%d-%b-%Y')} → {end.strftime('%d-%b-%Y')}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Trading Days</span>
                <span class="stat-value">{report.trading_days:,}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Expiries</span>
                <span class="stat-value">{report.expiry_count:,}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Contracts</span>
                <span class="stat-value">{report.contract_count:,}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Total Rows</span>
                <span class="stat-value">{report.row_count:,}</span>
            </div>
        </div>
        """
        st.markdown(stats_html, unsafe_allow_html=True)

    # Warnings
    if report.warnings:
        st.markdown("---")
        for warning in report.warnings:
            st.markdown(
                f'<div class="warning-badge">⚠️ {warning}</div>',
                unsafe_allow_html=True,
            )

    # Validation verdict
    if not report.is_valid:
        st.error(
            f"❌ Cannot proceed: missing required fields — "
            f"{', '.join(report.missing_required)}"
        )
    else:
        st.success("✅ Dataset is valid and ready for backtesting")
