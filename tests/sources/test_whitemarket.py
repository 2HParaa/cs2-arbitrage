from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage.sources.whitemarket import WhiteMarketError, WhiteMarketSource, fetch_items


@pytest.fixture(autouse=True)
def clear_fetch_items_cache():
    # fetch_items est mis en cache pour la durée du process (cf.
    # whitemarket.py) : sans ce nettoyage, un test récupérerait le
    # catalogue mocké d'un test précédent au lieu du sien.
    fetch_items.cache_clear()
    yield
    fetch_items.cache_clear()


CATALOG = [
    {
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
        "price": "30.690",
        "market_product_count": 1522,
    },
    {
        "market_hash_name": "AWP | Asiimov (Field-Tested)",
        "price": "65.500",
        "market_product_count": 65,
    },
]


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_get_price_returns_price(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = WhiteMarketSource()
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("30.690")
    assert price.currency == "USD"
    assert price.source == "whitemarket"


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_fetch_items_returns_raw_catalog(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    items = fetch_items()

    assert items == CATALOG


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_catalog_is_fetched_only_once(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = WhiteMarketSource()
    source.get_price("AK-47 | Redline (Field-Tested)")
    source.get_price("AWP | Asiimov (Field-Tested)")

    assert mock_get.call_count == 1


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_get_price_raises_when_item_not_found(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = WhiteMarketSource()

    with pytest.raises(WhiteMarketError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_get_price_warns_on_low_count(mock_get):
    catalog = [
        {"market_hash_name": "Item rare", "price": "1000.00", "market_product_count": 2},
    ]
    mock_get.return_value = _mock_get(catalog)

    source = WhiteMarketSource()

    with pytest.warns(UserWarning, match="Peu d'offres actives"):
        price = source.get_price("Item rare")

    assert price.amount == Decimal("1000.00")


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_get_price_does_not_warn_on_sufficient_count(mock_get, recwarn):
    mock_get.return_value = _mock_get(CATALOG)

    source = WhiteMarketSource()
    source.get_price("AK-47 | Redline (Field-Tested)")

    assert len(recwarn) == 0


def test_constructor_rejects_non_usd_currency():
    with pytest.raises(ValueError, match="USD"):
        WhiteMarketSource(currency="EUR")
