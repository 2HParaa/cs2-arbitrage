from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage.sources.skinport import SkinportError, SkinportSource

CATALOG = [
    {
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
        "currency": "EUR",
        "min_price": 12.34,
        "max_price": 15.0,
    },
    {
        "market_hash_name": "AWP | Asiimov (Field-Tested)",
        "currency": "EUR",
        "min_price": 65.5,
        "max_price": 80.0,
    },
]


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_get_price_returns_min_price(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = SkinportSource(currency="EUR")
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("12.34")
    assert price.currency == "EUR"
    assert price.source == "skinport"

    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"app_id": 730, "currency": "EUR"}


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_catalog_is_fetched_only_once(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = SkinportSource(currency="EUR")
    source.get_price("AK-47 | Redline (Field-Tested)")
    source.get_price("AWP | Asiimov (Field-Tested)")

    assert mock_get.call_count == 1


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_get_price_raises_when_item_not_found(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = SkinportSource()

    with pytest.raises(SkinportError):
        source.get_price("Item inexistant")
