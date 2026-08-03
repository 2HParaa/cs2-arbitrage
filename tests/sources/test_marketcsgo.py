from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage.sources.marketcsgo import MarketCSGOError, MarketCSGOSource, fetch_items

CATALOG = {
    "success": True,
    "currency": "USD",
    "items": [
        {"market_hash_name": "AK-47 | Redline (Field-Tested)", "price": "31.076", "volume": "525"},
        {"market_hash_name": "AWP | Asiimov (Field-Tested)", "price": "65.100", "volume": "65"},
    ],
}


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_get_price_returns_price(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = MarketCSGOSource()
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("31.076")
    assert price.currency == "USD"
    assert price.source == "marketcsgo"


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_fetch_items_returns_items_list(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    items = fetch_items()

    assert items == CATALOG["items"]


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_fetch_items_raises_when_response_unsuccessful(mock_get):
    mock_get.return_value = _mock_get({"success": False})

    with pytest.raises(MarketCSGOError, match="catalogue exploitable"):
        fetch_items()


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_catalog_is_fetched_only_once(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = MarketCSGOSource()
    source.get_price("AK-47 | Redline (Field-Tested)")
    source.get_price("AWP | Asiimov (Field-Tested)")

    assert mock_get.call_count == 1


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_get_price_raises_when_item_not_found(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = MarketCSGOSource()

    with pytest.raises(MarketCSGOError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_get_price_warns_on_low_volume(mock_get):
    catalog = {
        "success": True,
        "items": [{"market_hash_name": "Item rare", "price": "1000.00", "volume": "2"}],
    }
    mock_get.return_value = _mock_get(catalog)

    source = MarketCSGOSource()

    with pytest.warns(UserWarning, match="Peu d'offres actives"):
        price = source.get_price("Item rare")

    assert price.amount == Decimal("1000.00")


@patch("cs2_arbitrage.sources.marketcsgo.requests.get")
def test_get_price_does_not_warn_on_sufficient_volume(mock_get, recwarn):
    mock_get.return_value = _mock_get(CATALOG)

    source = MarketCSGOSource()
    source.get_price("AK-47 | Redline (Field-Tested)")

    assert len(recwarn) == 0


def test_constructor_rejects_non_usd_currency():
    with pytest.raises(ValueError, match="USD"):
        MarketCSGOSource(currency="EUR")
