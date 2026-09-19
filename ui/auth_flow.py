"""
Upstox OAuth2 authentication flow for Streamlit.

Handles the complete login flow:
1. User clicks "Connect to Upstox"
2. Opens auth URL in new tab
3. User logs in and is redirected back with ?code=...
4. We exchange code for access token
5. Token stored in session state
"""

from __future__ import annotations

import streamlit as st

from core.data_engine.upstox_client import UpstoxClient, UpstoxAuthError


def render_auth_flow() -> UpstoxClient | None:
    """
    Render the Upstox authentication UI.

    Returns:
        Authenticated UpstoxClient if connected, None otherwise.
    """
    # Check if already authenticated
    if "upstox_client" in st.session_state:
        client = st.session_state["upstox_client"]
        if client.is_authenticated:
            _render_connected(client)
            return client

    # Check for callback code in URL params
    query_params = st.query_params
    auth_code = query_params.get("code")

    if auth_code:
        return _handle_callback(auth_code)

    # Show connect button
    _render_connect_form()
    return None


def _render_connect_form():
    """Render the connection form with API key inputs."""
    st.markdown("""
    <div style="
        text-align: center;
        padding: 2rem;
        background: var(--bg-card, #151525);
        border: 1px solid var(--border, #2a2a3e);
        border-radius: 12px;
        margin: 1rem 0;
    ">
        <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">🔗</div>
        <h3 style="color: var(--text-primary, #e8e8f0); margin-bottom: 0.5rem;">
            Connect to Upstox
        </h3>
        <p style="color: var(--text-secondary, #8888aa); font-size: 0.9rem;">
            Paper trading requires a live data connection.
            Your credentials are stored only in this session.
        </p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️ API Credentials", expanded=True):
        api_key = st.text_input(
            "API Key",
            value=st.session_state.get("upstox_api_key", ""),
            type="default",
            help="From Upstox Developer Console → Your App → API Key",
        )
        api_secret = st.text_input(
            "API Secret",
            value=st.session_state.get("upstox_api_secret", ""),
            type="password",
            help="From Upstox Developer Console → Your App → API Secret",
        )
        redirect_uri = st.text_input(
            "Redirect URI",
            value="http://localhost:8501/callback",
            help="Must match what you set in Upstox Developer Console",
        )

        if api_key and api_secret:
            st.session_state["upstox_api_key"] = api_key
            st.session_state["upstox_api_secret"] = api_secret

            client = UpstoxClient(
                api_key=api_key,
                api_secret=api_secret,
                redirect_uri=redirect_uri,
            )

            try:
                auth_url = client.get_auth_url()
                st.session_state["upstox_client_pending"] = client

                st.link_button(
                    "🚀 Login with Upstox",
                    auth_url,
                    width="stretch",
                    type="primary",
                )
                st.caption(
                    "After logging in, you'll be redirected back here "
                    "and connected automatically."
                )

            except UpstoxAuthError as e:
                st.error(f"Auth error: {e}")
        else:
            st.info(
                "Enter your API credentials from "
                "[Upstox Developer Console](https://account.upstox.com/developer/apps)"
            )

    # Manual token input (for power users)
    with st.expander("🔑 Or paste Access Token directly"):
        manual_token = st.text_input(
            "Access Token",
            type="password",
            help="If you already have a token from another tool",
        )
        if manual_token and st.button("Connect with Token"):
            client = UpstoxClient(access_token=manual_token)
            st.session_state["upstox_client"] = client
            st.rerun()


def _handle_callback(auth_code: str) -> UpstoxClient | None:
    """Handle the OAuth2 callback with the authorization code."""
    client = st.session_state.get("upstox_client_pending")

    if client is None:
        # Try from env
        client = UpstoxClient()

    if not client.api_key:
        st.error("No API key found. Please enter credentials first.")
        return None

    try:
        with st.spinner("Exchanging authorization code..."):
            client.exchange_code(auth_code)

        st.session_state["upstox_client"] = client

        # Clear the code from URL params
        st.query_params.clear()
        st.rerun()

    except UpstoxAuthError as e:
        st.error(f"Authentication failed: {e}")
        st.query_params.clear()
        return None

    return client


def _render_connected(client: UpstoxClient):
    """Render the connected status badge."""
    st.markdown("""
    <div style="
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        background: rgba(0, 210, 106, 0.1);
        border: 1px solid rgba(0, 210, 106, 0.3);
        border-radius: 10px;
        margin-bottom: 1rem;
    ">
        <span style="font-size: 1.2rem;">🟢</span>
        <div>
            <div style="color: #00d26a; font-weight: 600; font-size: 0.9rem;">
                Connected to Upstox
            </div>
            <div style="color: var(--text-dim, #555570); font-size: 0.75rem;">
                Live data feed active
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Disconnect", type="secondary"):
        del st.session_state["upstox_client"]
        st.rerun()
