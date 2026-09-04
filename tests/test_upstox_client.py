"""
Tests for Upstox API client and LiveDataProvider.

Uses mock responses to test OAuth2 authentication, option chain conversion,
LTP retrieval, Greeks, and MarketState creation without real network requests.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.data_engine.providers import LiveDataProvider
from core.data_engine.schema import MarketState, OptionType, Side
from core.data_engine.upstox_client import (
    UpstoxAPIError,
    UpstoxAuthError,
    UpstoxClient,
    create_client_from_env,
)


# ── Sample Fixtures ──────────────────────────────────────────────────


SAMPLE_OPTION_CHAIN_RESPONSE = {
    "status": "success",
    "data": [
        {
            "expiry": "2026-09-10",
            "pcr": 0.95,
            "strike_price": 24500.0,
            "underlying_key": "NSE_INDEX|Nifty 50",
            "underlying_spot_price": 24520.5,
            "call_options": {
                "instrument_key": "NSE_FO|10001",
                "market_data": {
                    "ltp": 125.5,
                    "volume": 50000,
                    "oi": 150000,
                    "bid_price": 125.0,
                    "ask_price": 126.0,
                    "open": 110.0,
                    "high": 135.0,
                    "low": 105.0,
                },
                "option_greeks": {
                    "iv": 13.5,
                    "delta": 0.52,
                    "theta": -15.2,
                    "gamma": 0.001,
                    "vega": 18.4,
                },
            },
            "put_options": {
                "instrument_key": "NSE_FO|10002",
                "market_data": {
                    "ltp": 105.0,
                    "volume": 42000,
                    "oi": 130000,
                    "bid_price": 104.5,
                    "ask_price": 105.5,
                    "open": 120.0,
                    "high": 125.0,
                    "low": 98.0,
                },
                "option_greeks": {
                    "iv": 14.1,
                    "delta": -0.48,
                    "theta": -14.8,
                    "gamma": 0.001,
                    "vega": 17.9,
                },
            },
        },
        {
            "expiry": "2026-09-10",
            "pcr": 1.10,
            "strike_price": 24600.0,
            "underlying_spot_price": 24520.5,
            "call_options": {
                "instrument_key": "NSE_FO|10003",
                "market_data": {
                    "ltp": 75.0,
                    "volume": 35000,
                    "oi": 95000,
                    "bid_price": 74.5,
                    "ask_price": 75.5,
                    "open": 80.0,
                    "high": 85.0,
                    "low": 70.0,
                },
            },
            "put_options": {
                "instrument_key": "NSE_FO|10004",
                "market_data": {
                    "ltp": 155.0,
                    "volume": 60000,
                    "oi": 180000,
                    "bid_price": 154.5,
                    "ask_price": 155.5,
                    "open": 140.0,
                    "high": 160.0,
                    "low": 138.0,
                },
            },
        },
    ],
}


class TestUpstoxClientAuth:
    """Test OAuth2 authentication logic in UpstoxClient."""

    def test_init_and_auth_status(self):
        client_unauth = UpstoxClient(api_key="key123", api_secret="sec123")
        assert not client_unauth.is_authenticated

        client_auth = UpstoxClient(access_token="tok123")
        assert client_auth.is_authenticated

    def test_headers_raises_when_unauthenticated(self):
        client = UpstoxClient()
        with pytest.raises(UpstoxAuthError, match="Not authenticated"):
            _ = client._headers

    def test_headers_returns_bearer_token(self):
        client = UpstoxClient(access_token="test_token")
        headers = client._headers
        assert headers["Authorization"] == "Bearer test_token"
        assert headers["Accept"] == "application/json"

    def test_get_auth_url(self):
        client = UpstoxClient(
            api_key="my_key",
            api_secret="my_secret",
            redirect_uri="http://localhost:8501/callback",
        )
        url = client.get_auth_url()
        assert "client_id=my_key" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8501%2Fcallback" in url or "redirect_uri=http://localhost:8501/callback" in url
        assert "response_type=code" in url

    def test_get_auth_url_without_key_raises(self):
        client = UpstoxClient(api_key="")
        with pytest.raises(UpstoxAuthError, match="API key not set"):
            client.get_auth_url()

    @patch("requests.Session.post")
    def test_exchange_code_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new_access_token_123"}
        mock_post.return_value = mock_response

        client = UpstoxClient(api_key="key", api_secret="secret")
        token = client.exchange_code("auth_code_xyz")

        assert token == "new_access_token_123"
        assert client.access_token == "new_access_token_123"
        assert client.is_authenticated

    @patch("requests.Session.post")
    def test_exchange_code_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        client = UpstoxClient(api_key="key", api_secret="secret")
        with pytest.raises(UpstoxAuthError, match="Token exchange failed: 401"):
            client.exchange_code("invalid_code")


class TestUpstoxClientMarketData:
    """Test market data queries with UpstoxClient."""

    @patch("requests.Session.get")
    def test_get_nifty_ltp_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "NSE_INDEX|Nifty 50": {
                    "last_price": 24520.50,
                    "instrument_token": "256265",
                }
            },
        }
        mock_get.return_value = mock_response

        client = UpstoxClient(access_token="valid_token")
        ltp = client.get_nifty_ltp()
        assert ltp == 24520.50

    @patch("requests.Session.get")
    def test_get_nifty_ltp_failure(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        mock_get.return_value = mock_response

        client = UpstoxClient(access_token="valid_token")
        with pytest.raises(UpstoxAPIError, match="LTP fetch failed: 500"):
            client.get_nifty_ltp()

    @patch("requests.Session.get")
    def test_get_option_chain_parses_canonical(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_OPTION_CHAIN_RESPONSE
        mock_get.return_value = mock_response

        client = UpstoxClient(access_token="valid_token")
        df = client.get_option_chain(expiry="2026-09-10")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 4  # 2 strikes × (CE + PE)

        # Canonical columns must exist
        expected_cols = [
            "timestamp", "underlying", "underlying_close", "expiry",
            "strike", "option_type", "open", "high", "low", "close",
            "volume", "oi", "bid", "ask",
        ]
        for col in expected_cols:
            assert col in df.columns

        # Verify specific values
        ce_24500 = df[(df["strike"] == 24500.0) & (df["option_type"] == "CE")].iloc[0]
        assert ce_24500["close"] == 125.5
        assert ce_24500["bid"] == 125.0
        assert ce_24500["ask"] == 126.0
        assert ce_24500["underlying_close"] == 24520.5
        assert ce_24500["underlying"] == "NIFTY"

        pe_24600 = df[(df["strike"] == 24600.0) & (df["option_type"] == "PE")].iloc[0]
        assert pe_24600["close"] == 155.0
        assert pe_24600["volume"] == 60000

    @patch("requests.Session.get")
    def test_get_option_greeks(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "NSE_FO|10001": {
                    "iv": 14.5,
                    "delta": 0.55,
                    "gamma": 0.002,
                    "theta": -12.0,
                    "vega": 16.0,
                }
            },
        }
        mock_get.return_value = mock_response

        client = UpstoxClient(access_token="valid_token")
        df_greeks = client.get_option_greeks(["NSE_FO|10001"])

        assert not df_greeks.empty
        assert "delta" in df_greeks.columns
        assert df_greeks.iloc[0]["delta"] == 0.55

    @patch("requests.Session.get")
    def test_get_market_data_feed_url(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "authorizedRedirectUri": "wss://api.upstox.com/v3/feed/market-data-feed?code=123"
            },
        }
        mock_get.return_value = mock_response

        client = UpstoxClient(access_token="valid_token")
        ws_url = client.get_market_data_feed_url()
        assert ws_url.startswith("wss://api.upstox.com")


class TestLiveDataProvider:
    """Test LiveDataProvider integration with UpstoxClient."""

    def test_get_market_state_success(self):
        client = MagicMock(spec=UpstoxClient)
        client.get_nifty_ltp.return_value = 24500.0

        # Canonical option chain dataframe
        df_chain = pd.DataFrame([
            {
                "timestamp": datetime.now(),
                "underlying": "NIFTY",
                "underlying_close": 24500.0,
                "expiry": pd.Timestamp("2026-09-10"),
                "strike": 24500.0,
                "option_type": "CE",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 105.0,
                "volume": 1000,
                "oi": 5000,
                "bid": 104.5,
                "ask": 105.5,
            },
            {
                "timestamp": datetime.now(),
                "underlying": "NIFTY",
                "underlying_close": 24500.0,
                "expiry": pd.Timestamp("2026-09-10"),
                "strike": 24500.0,
                "option_type": "PE",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 95.0,
                "volume": 1000,
                "oi": 5000,
                "bid": 94.5,
                "ask": 95.5,
            },
        ])
        client.get_option_chain.return_value = df_chain

        provider = LiveDataProvider(client)
        state = provider.get_market_state()

        assert isinstance(state, MarketState)
        assert state.underlying == "NIFTY"
        assert state.underlying_close == 24500.0
        assert not state.option_chain.empty
        assert state.get_atm_strike() == 24500.0
        assert state.get_option_price(24500.0, OptionType.CE) == 105.0
        assert state.get_option_price(24500.0, OptionType.PE) == 95.0

    def test_get_market_state_handles_api_exception(self):
        client = MagicMock(spec=UpstoxClient)
        client.get_nifty_ltp.side_effect = Exception("Network timeout")

        provider = LiveDataProvider(client)
        state = provider.get_market_state()

        assert isinstance(state, MarketState)
        assert state.option_chain.empty
        assert state.underlying_close == 0.0

    def test_get_trading_dates(self):
        client = MagicMock(spec=UpstoxClient)
        provider = LiveDataProvider(client)
        today = date.today()
        dates = provider.get_trading_dates(today, today)
        assert dates == [today]
