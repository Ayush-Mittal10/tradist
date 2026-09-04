"""
Upstox API client wrapper.

Provides authenticated access to Upstox v2/v3 APIs for:
- OAuth2 authentication flow
- NIFTY option chain data (→ canonical DataFrame format)
- NIFTY spot price (LTP)
- Option Greeks
- WebSocket market feed

All data is transformed into the same canonical format used by
the CSV parser, so LiveDataProvider can feed identical MarketState
objects to strategies.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, date
from typing import Callable, Any

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────

UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
UPSTOX_BASE_URL = "https://api.upstox.com"

NIFTY_INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"


class UpstoxAuthError(Exception):
    """Raised when authentication fails."""
    pass


class UpstoxAPIError(Exception):
    """Raised when an API call fails."""
    pass


class UpstoxClient:
    """
    Authenticated Upstox API client.

    Handles OAuth2 flow and provides methods to fetch market data
    in the canonical format used by the rest of the system.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        redirect_uri: str | None = None,
        access_token: str | None = None,
    ):
        """
        Initialize Upstox client.

        Args:
            api_key: Upstox API Key (or from UPSTOX_API_KEY env var)
            api_secret: Upstox API Secret (or from UPSTOX_API_SECRET env var)
            redirect_uri: OAuth2 redirect URI (or from UPSTOX_REDIRECT_URI env var)
            access_token: Pre-existing access token (skip auth flow)
        """
        self.api_key = api_key or os.environ.get("UPSTOX_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("UPSTOX_API_SECRET", "")
        self.redirect_uri = redirect_uri or os.environ.get(
            "UPSTOX_REDIRECT_URI", "http://localhost:8501/callback"
        )
        self.access_token = access_token
        self._session = requests.Session()

    @property
    def is_authenticated(self) -> bool:
        """Check if client has a valid access token."""
        return bool(self.access_token)

    @property
    def _headers(self) -> dict:
        """Build authorization headers."""
        if not self.access_token:
            raise UpstoxAuthError("Not authenticated. Call get_auth_url() and exchange_code() first.")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    # ── OAuth2 Flow ───────────────────────────────────────────────────

    def get_auth_url(self) -> str:
        """
        Generate OAuth2 authorization URL.

        User should be redirected to this URL to log in.
        After login, Upstox redirects to redirect_uri with ?code=...
        """
        if not self.api_key:
            raise UpstoxAuthError("API key not set. Check .env file or constructor args.")

        return (
            f"{UPSTOX_AUTH_URL}"
            f"?client_id={self.api_key}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
        )

    def exchange_code(self, auth_code: str) -> str:
        """
        Exchange authorization code for access token.

        Args:
            auth_code: The code received from the OAuth2 redirect

        Returns:
            Access token string
        """
        payload = {
            "code": auth_code,
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        response = self._session.post(
            UPSTOX_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise UpstoxAuthError(f"Token exchange failed: {response.status_code} — {response.text}")

        data = response.json()
        self.access_token = data.get("access_token")

        if not self.access_token:
            raise UpstoxAuthError(f"No access_token in response: {data}")

        return self.access_token

    # ── Market Data ───────────────────────────────────────────────────

    def get_nifty_ltp(self) -> float:
        """
        Get NIFTY 50 last traded price.

        Returns:
            Current NIFTY price
        """
        url = f"{UPSTOX_BASE_URL}/v2/market-quote/ltp"
        params = {"instrument_key": NIFTY_INSTRUMENT_KEY}

        response = self._session.get(url, params=params, headers=self._headers)

        if response.status_code != 200:
            raise UpstoxAPIError(f"LTP fetch failed: {response.status_code} — {response.text}")

        data = response.json()
        # Navigate the response structure
        quotes = data.get("data", {})
        for key, value in quotes.items():
            if "ltp" in value or "last_price" in value:
                return float(value.get("ltp", value.get("last_price", 0)))

        raise UpstoxAPIError(f"Could not extract LTP from response: {data}")

    def get_option_chain(
        self,
        expiry: str = "current_week",
    ) -> pd.DataFrame:
        """
        Fetch NIFTY option chain and convert to canonical format.

        Args:
            expiry: Expiry date (YYYY-MM-DD) or keywords:
                    "current_week", "next_week", "current_month"

        Returns:
            DataFrame in canonical format (same columns as CSV parser output)
        """
        url = f"{UPSTOX_BASE_URL}/v2/option/chain"
        params = {
            "instrument_key": NIFTY_INSTRUMENT_KEY,
            "expiry_date": expiry,
        }

        response = self._session.get(url, params=params, headers=self._headers)

        if response.status_code != 200:
            raise UpstoxAPIError(f"Option chain fetch failed: {response.status_code} — {response.text}")

        data = response.json()
        return self._parse_option_chain(data)

    def get_option_greeks(
        self,
        instrument_keys: list[str],
    ) -> pd.DataFrame:
        """
        Fetch IV and Greeks from Upstox v3 API.

        Args:
            instrument_keys: List of option instrument keys

        Returns:
            DataFrame with iv, delta, gamma, theta, vega columns
        """
        url = f"{UPSTOX_BASE_URL}/v3/market-quote/option-greek"

        # API may limit batch size
        all_data = []
        batch_size = 50

        for i in range(0, len(instrument_keys), batch_size):
            batch = instrument_keys[i:i + batch_size]
            params = {"instrument_key": ",".join(batch)}

            response = self._session.get(url, params=params, headers=self._headers)

            if response.status_code == 200:
                data = response.json()
                greeks_data = data.get("data", {})
                for key, vals in greeks_data.items():
                    all_data.append({
                        "instrument_key": key,
                        "iv": vals.get("iv", 0),
                        "delta": vals.get("delta", 0),
                        "gamma": vals.get("gamma", 0),
                        "theta": vals.get("theta", 0),
                        "vega": vals.get("vega", 0),
                    })

        return pd.DataFrame(all_data) if all_data else pd.DataFrame()

    def get_market_data_feed_url(self) -> str:
        """
        Get authorized WebSocket feed URL from Upstox v3 API.

        Returns:
            Authorized WebSocket connection URL.
        """
        url = f"{UPSTOX_BASE_URL}/v3/feed/market-data-feed/authorize"
        response = self._session.get(url, headers=self._headers)

        if response.status_code != 200:
            raise UpstoxAPIError(f"WebSocket auth failed: {response.status_code} — {response.text}")

        data = response.json()
        payload = data.get("data", {})
        redirect_uri = payload.get("authorizedRedirectUri") or payload.get("authorized_redirect_uri")
        if not redirect_uri:
            raise UpstoxAPIError(f"No authorizedRedirectUri in response: {data}")
        return redirect_uri

    def start_websocket(
        self,
        instruments: list[str],
        on_message: Callable[[Any], None],
        on_error: Callable[[Any], None] | None = None,
        on_close: Callable[[Any, Any], None] | None = None,
    ) -> threading.Thread:
        """
        Start WebSocket feed in a background thread for real-time market data ticks.

        Args:
            instruments: List of instrument keys (e.g., ["NSE_INDEX|Nifty 50"])
            on_message: Callback invoked with received message
            on_error: Optional error callback
            on_close: Optional close callback

        Returns:
            Started background threading.Thread
        """
        import websocket

        ws_url = self.get_market_data_feed_url()

        def _on_open(ws):
            sub_payload = {
                "guid": "tradist_quant_lab",
                "method": "sub",
                "params": {
                    "mode": "full",
                    "instrumentKeys": instruments,
                },
            }
            ws.send(json.dumps(sub_payload).encode("utf-8"))

        def _run():
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=_on_open,
                on_message=lambda ws, msg: on_message(msg),
                on_error=lambda ws, err: on_error(err) if on_error else None,
                on_close=lambda ws, code, msg: on_close(code, msg) if on_close else None,
            )
            ws.run_forever()

        ws_thread = threading.Thread(target=_run, daemon=True, name="upstox-ws-feed")
        ws_thread.start()
        return ws_thread

    # ── Response Parsing ──────────────────────────────────────────────

    def _parse_option_chain(self, api_response: dict) -> pd.DataFrame:
        """
        Convert Upstox option chain API response to canonical DataFrame.

        The canonical format matches what csv_parser produces, so
        LiveDataProvider can create identical MarketState objects.
        """
        rows = []
        now = datetime.now()

        chain_data = api_response.get("data", [])
        if not chain_data:
            return pd.DataFrame()

        for entry in chain_data:
            # Each entry has 'call_options' and 'put_options'
            expiry_str = entry.get("expiry", "")
            strike = float(entry.get("strike_price", 0))
            underlying_close = float(entry.get("underlying_spot_price", 0))

            # Parse expiry
            try:
                expiry_dt = pd.Timestamp(expiry_str)
            except Exception:
                continue

            # Process call side
            call_data = entry.get("call_options", {})
            if call_data:
                market = call_data.get("market_data", {})
                rows.append(self._build_row(
                    now, underlying_close, expiry_dt, strike, "CE", market
                ))

            # Process put side
            put_data = entry.get("put_options", {})
            if put_data:
                market = put_data.get("market_data", {})
                rows.append(self._build_row(
                    now, underlying_close, expiry_dt, strike, "PE", market
                ))

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df

    def _build_row(
        self,
        timestamp: datetime,
        underlying_close: float,
        expiry: pd.Timestamp,
        strike: float,
        option_type: str,
        market_data: dict,
    ) -> dict:
        """Build a single row in canonical format from API market data."""
        ltp = float(market_data.get("ltp", 0))
        bid = float(market_data.get("bid_price", 0))
        ask = float(market_data.get("ask_price", 0))
        volume = int(market_data.get("volume", 0))
        oi = int(market_data.get("oi", market_data.get("open_interest", 0)))
        high = float(market_data.get("high", ltp))
        low = float(market_data.get("low", ltp))
        open_price = float(market_data.get("open", ltp))

        return {
            "timestamp": timestamp,
            "underlying": "NIFTY",
            "underlying_close": underlying_close,
            "expiry": expiry,
            "strike": strike,
            "option_type": option_type,
            "open": open_price,
            "high": high,
            "low": low,
            "close": ltp,  # LTP is the "close" in live context
            "volume": volume,
            "oi": oi,
            "bid": bid if bid > 0 else np.nan,
            "ask": ask if ask > 0 else np.nan,
        }


def create_client_from_env() -> UpstoxClient:
    """
    Create an UpstoxClient from environment variables.

    Expects UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI
    in .env file or environment.
    """
    load_dotenv()
    return UpstoxClient()
