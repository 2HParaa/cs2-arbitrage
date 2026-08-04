from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage.sources.waxpeer import WaxpeerError, WaxpeerSource, fetch_items


@pytest.fixture(autouse=True)
def clear_fetch_items_cache():
    # fetch_items est mis en cache pour la durée du process (cf.
    # waxpeer.py) : sans ce nettoyage, un test récupérerait le catalogue
    # mocké d'un test précédent au lieu du sien.
    fetch_items.cache_clear()
    yield
    fetch_items.cache_clear()


CATALOG = {
    "success": True,
    "items": [
        {"name": "AK-47 | Redline (Field-Tested)", "count": 112, "min": 14450, "img": "a.webp"},
        {"name": "AWP | Asiimov (Field-Tested)", "count": 65, "min": 6550, "img": "b.webp"},
    ],
}


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_get_price_returns_min_price_converted_from_thousandths(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = WaxpeerSource()
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("14.45")
    assert price.currency == "USD"
    assert price.source == "waxpeer"

    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"game": "csgo"}


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_fetch_items_returns_raw_catalog(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    items = fetch_items()

    assert items == CATALOG["items"]


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_catalog_is_fetched_only_once(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = WaxpeerSource()
    source.get_price("AK-47 | Redline (Field-Tested)")
    source.get_price("AWP | Asiimov (Field-Tested)")

    assert mock_get.call_count == 1


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_get_price_raises_when_item_not_found(mock_get):
    mock_get.return_value = _mock_get(CATALOG)

    source = WaxpeerSource()

    with pytest.raises(WaxpeerError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_get_price_warns_on_low_count(mock_get):
    catalog = {
        "success": True,
        "items": [{"name": "Item rare", "count": 2, "min": 100000, "img": "c.webp"}],
    }
    mock_get.return_value = _mock_get(catalog)

    source = WaxpeerSource()

    with pytest.warns(UserWarning, match="Peu d'offres actives"):
        price = source.get_price("Item rare")

    assert price.amount == Decimal("100.00")


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_get_price_does_not_warn_on_sufficient_count(mock_get, recwarn):
    mock_get.return_value = _mock_get(CATALOG)

    source = WaxpeerSource()
    source.get_price("AK-47 | Redline (Field-Tested)")

    assert len(recwarn) == 0


def test_constructor_rejects_non_usd_currency():
    with pytest.raises(ValueError, match="USD"):
        WaxpeerSource(currency="EUR")
