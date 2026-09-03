"""
Streamlit theme and styling configuration.

Premium dark theme with glassmorphism effects and the lab's color palette.
"""

import streamlit as st


def configure_page():
    """Set page config and inject custom CSS."""
    st.set_page_config(
        page_title="NIFTY Quant Lab",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(get_custom_css(), unsafe_allow_html=True)


def get_custom_css() -> str:
    """Return custom CSS for the premium dark theme."""
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    /* ── Root variables ─────────────────────────────────────────── */
    :root {
        --bg-primary: #0a0a14;
        --bg-secondary: #0f0f1a;
        --bg-card: #151525;
        --bg-card-hover: #1a1a2e;
        --border: #2a2a3e;
        --border-accent: #4f8cff33;
        --text-primary: #e8e8f0;
        --text-secondary: #8888aa;
        --text-dim: #555570;
        --accent: #4f8cff;
        --accent-glow: #4f8cff44;
        --profit: #00d26a;
        --profit-bg: #00d26a18;
        --loss: #ff4757;
        --loss-bg: #ff475718;
        --warning: #ffa502;
        --warning-bg: #ffa50218;
        --gradient-start: #4f8cff;
        --gradient-end: #a855f7;
    }

    /* ── Global overrides ───────────────────────────────────────── */
    .stApp {
        background: var(--bg-primary) !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* ── Header ─────────────────────────────────────────────────── */
    .lab-header {
        background: linear-gradient(135deg, var(--bg-secondary), var(--bg-card));
        border-bottom: 1px solid var(--border);
        padding: 1.5rem 2rem;
        margin: -1rem -1rem 2rem -1rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .lab-header h1 {
        font-size: 1.6rem;
        font-weight: 700;
        background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        letter-spacing: -0.03em;
    }

    .lab-header .subtitle {
        font-size: 0.85rem;
        color: var(--text-secondary);
        font-weight: 400;
    }

    /* ── Metric cards ───────────────────────────────────────────── */
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        transition: all 0.2s ease;
    }

    .metric-card:hover {
        border-color: var(--border-accent);
        background: var(--bg-card-hover);
        transform: translateY(-1px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }

    .metric-label {
        font-size: 0.75rem;
        font-weight: 500;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.35rem;
    }

    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary);
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: -0.02em;
    }

    .metric-value.profit { color: var(--profit); }
    .metric-value.loss { color: var(--loss); }

    .metric-subtext {
        font-size: 0.7rem;
        color: var(--text-dim);
        margin-top: 0.25rem;
    }

    /* ── Section headers ────────────────────────────────────────── */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border);
    }

    /* ── Config panel ───────────────────────────────────────────── */
    .config-panel {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1.5rem;
    }

    /* ── Warning badges ─────────────────────────────────────────── */
    .warning-badge {
        background: var(--warning-bg);
        border: 1px solid var(--warning);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        font-size: 0.85rem;
        color: var(--warning);
    }

    /* ── Data validation ────────────────────────────────────────── */
    .field-check {
        display: flex;
        align-items: center;
        padding: 0.4rem 0;
        font-size: 0.9rem;
    }

    .field-check .icon { margin-right: 0.5rem; }
    .field-check.detected { color: var(--profit); }
    .field-check.missing { color: var(--warning); }

    .dataset-stats {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1.25rem;
        margin: 1rem 0;
    }

    .dataset-stats .stat {
        display: flex;
        justify-content: space-between;
        padding: 0.4rem 0;
        border-bottom: 1px solid var(--border);
    }

    .dataset-stats .stat:last-child {
        border-bottom: none;
    }

    .dataset-stats .stat-label {
        color: var(--text-secondary);
        font-size: 0.85rem;
    }

    .dataset-stats .stat-value {
        color: var(--text-primary);
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
    }

    /* ── Trade table ────────────────────────────────────────────── */
    .stDataFrame {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }

    /* ── Buttons ────────────────────────────────────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end)) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        padding: 0.75rem 2rem !important;
        transition: all 0.3s ease !important;
        letter-spacing: 0.02em !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px var(--accent-glow) !important;
    }

    /* ── Tabs ───────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background: var(--bg-secondary);
        border-radius: 12px;
        padding: 0.25rem;
        border: 1px solid var(--border);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        padding: 0.75rem 1.5rem !important;
        font-weight: 500 !important;
        color: var(--text-secondary) !important;
        background: transparent !important;
    }

    .stTabs [aria-selected="true"] {
        background: var(--bg-card) !important;
        color: var(--accent) !important;
        border: 1px solid var(--border-accent) !important;
    }

    /* ── Selectbox / Input styling ──────────────────────────────── */
    .stSelectbox > div > div,
    .stNumberInput > div > div > input,
    .stTextInput > div > div > input {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
    }

    /* ── File uploader ──────────────────────────────────────────── */
    .stFileUploader > div {
        background: var(--bg-card) !important;
        border: 2px dashed var(--border) !important;
        border-radius: 12px !important;
    }

    .stFileUploader > div:hover {
        border-color: var(--accent) !important;
    }

    /* ── Expander ───────────────────────────────────────────────── */
    .streamlit-expanderHeader {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
    }

    /* ── Plotly chart container ──────────────────────────────────── */
    .js-plotly-plot {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid var(--border);
    }

    /* ── Scrollbar ──────────────────────────────────────────────── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-primary); }
    ::-webkit-scrollbar-thumb {
        background: var(--border);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }

    </style>
    """


def render_header():
    """Render the app header."""
    st.markdown("""
    <div class="lab-header">
        <div>
            <h1>🔬 NIFTY Quant Lab</h1>
            <div class="subtitle">Options Research & Paper Trading Laboratory</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_metric_card(label: str, value: str, is_profit: bool | None = None, subtext: str = ""):
    """Render a single metric card."""
    value_class = "metric-value"
    if is_profit is True:
        value_class += " profit"
    elif is_profit is False:
        value_class += " loss"

    subtext_html = f'<div class="metric-subtext">{subtext}</div>' if subtext else ""

    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="{value_class}">{value}</div>
        {subtext_html}
    </div>
    """, unsafe_allow_html=True)
