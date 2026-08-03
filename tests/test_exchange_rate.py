from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import requests

from cs2_arbitrage.exchange_rate import ExchangeRateError, fetch_usd_to_eur_rate


@pytest.fixture(autouse=True)
def clear_cache():
    fetch_usd_to_eur_rate.cache_clear()
    yield
    fetch_usd_to_eur_rate.cache_clear()


@patch("cs2_arbitrage.exchange_rate.requests.get")
def test_fetch_usd_to_eur_rate_returns_rate(mock_get):
    mock_get.return_value = Mock(
        raise_for_status=Mock(), json=Mock(return_value={"rates": {"EUR": 0.8669}})
    )

    rate = fetch_usd_to_eur_rate()

    assert rate == Decimal("0.8669")
    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"from": "USD", "to": "EUR"}


@patch("cs2_arbitrage.exchange_rate.requests.get")
def test_fetch_usd_to_eur_rate_is_cached(mock_get):
    mock_get.return_value = Mock(
        raise_for_status=Mock(), json=Mock(return_value={"rates": {"EUR": 0.8669}})
    )

    fetch_usd_to_eur_rate()
    fetch_usd_to_eur_rate()

    assert mock_get.call_count == 1


@patch("cs2_arbitrage.exchange_rate.requests.get")
def test_fetch_usd_to_eur_rate_raises_on_network_error(mock_get):
    mock_get.side_effect = requests.ConnectionError("boom")

    with pytest.raises(ExchangeRateError):
        fetch_usd_to_eur_rate()


@patch("cs2_arbitrage.exchange_rate.requests.get")
def test_fetch_usd_to_eur_rate_raises_on_unexpected_response_shape(mock_get):
    mock_get.return_value = Mock(raise_for_status=Mock(), json=Mock(return_value={}))

    with pytest.raises(ExchangeRateError):
        fetch_usd_to_eur_rate()
