from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage.sources.csdeals import CSDealsError, CSDealsSource, fetch_items

RAW_RESPONSE = {
    "success": True,
    "response": {
        "time_updated": 1785684056,
        "appid": 730,
        "items": [
            {"marketname": "AK-47 | Redline (Field-Tested)", "lowest_price": "136.98"},
            {"marketname": "AWP | Asiimov (Field-Tested)", "lowest_price": "65.50"},
        ],
    },
}


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


@patch("cs2_arbitrage.sources.csdeals.requests.get")
def test_get_price_returns_lowest_price(mock_get):
    mock_get.return_value = _mock_get(RAW_RESPONSE)

    source = CSDealsSource()
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("136.98")
    assert price.currency == "USD"
    assert price.source == "csdeals"

    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"appid": 730}


@patch("cs2_arbitrage.sources.csdeals.requests.get")
def test_fetch_items_returns_raw_catalog(mock_get):
    mock_get.return_value = _mock_get(RAW_RESPONSE)

    items = fetch_items()

    assert items == RAW_RESPONSE["response"]["items"]


@patch("cs2_arbitrage.sources.csdeals.requests.get")
def test_catalog_is_fetched_only_once(mock_get):
    mock_get.return_value = _mock_get(RAW_RESPONSE)

    source = CSDealsSource()
    source.get_price("AK-47 | Redline (Field-Tested)")
    source.get_price("AWP | Asiimov (Field-Tested)")

    assert mock_get.call_count == 1


@patch("cs2_arbitrage.sources.csdeals.requests.get")
def test_get_price_raises_when_item_not_found(mock_get):
    mock_get.return_value = _mock_get(RAW_RESPONSE)

    source = CSDealsSource()

    with pytest.raises(CSDealsError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.csdeals.requests.get")
def test_fetch_items_raises_when_response_unsuccessful(mock_get):
    mock_get.return_value = _mock_get({"success": False})

    with pytest.raises(CSDealsError, match="catalogue exploitable"):
        fetch_items()


def test_constructor_rejects_non_usd_currency():
    with pytest.raises(ValueError, match="USD"):
        CSDealsSource(currency="EUR")
