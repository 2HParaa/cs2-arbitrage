from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage.sources.steam import SteamMarketError, SteamMarketSource


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_parses_eur_price(mock_get):
    mock_get.return_value = _mock_get({"success": True, "lowest_price": "12,34€"})

    source = SteamMarketSource(currency="EUR")
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("12.34")
    assert price.currency == "EUR"
    assert price.source == "steam"

    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "appid": 730,
        "currency": 3,
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
    }


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_parses_usd_price_with_thousands_separator(mock_get):
    mock_get.return_value = _mock_get({"success": True, "lowest_price": "$1,234.56"})

    source = SteamMarketSource(currency="USD")
    price = source.get_price("Karambit | Doppler")

    assert price.amount == Decimal("1234.56")
    assert price.currency == "USD"


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_parses_eur_price_with_thousands_separator(mock_get):
    mock_get.return_value = _mock_get({"success": True, "lowest_price": "1 234,56€"})

    source = SteamMarketSource(currency="EUR")
    price = source.get_price("Karambit | Doppler")

    assert price.amount == Decimal("1234.56")


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_raises_when_item_not_found(mock_get):
    mock_get.return_value = _mock_get({"success": False})

    source = SteamMarketSource()

    with pytest.raises(SteamMarketError):
        source.get_price("Item inexistant")
