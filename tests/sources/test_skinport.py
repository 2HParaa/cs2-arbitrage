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

    with pytest.raises(SkinportError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_get_price_raises_when_no_active_listing(mock_get):
    catalog = [
        {
            "market_hash_name": "Item sans offre",
            "currency": "EUR",
            "min_price": None,
            "max_price": None,
            "quantity": 0,
        }
    ]
    mock_get.return_value = _mock_get(catalog)

    source = SkinportSource()

    with pytest.raises(SkinportError, match="Aucune offre de vente active"):
        source.get_price("Item sans offre")


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_get_price_warns_on_low_quantity(mock_get):
    catalog = [
        {
            "market_hash_name": "AK-47 | Redline (Field-Tested)",
            "currency": "EUR",
            "min_price": 12.34,
            "max_price": 15.0,
            "quantity": 3,
        }
    ]
    mock_get.return_value = _mock_get(catalog)

    source = SkinportSource(currency="EUR")

    with pytest.warns(UserWarning, match="Peu d'offres actives"):
        price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.amount == Decimal("12.34")


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_get_price_does_not_warn_on_sufficient_quantity(mock_get, recwarn):
    catalog = [
        {
            "market_hash_name": "AK-47 | Redline (Field-Tested)",
            "currency": "EUR",
            "min_price": 12.34,
            "max_price": 15.0,
            "quantity": 50,
        }
    ]
    mock_get.return_value = _mock_get(catalog)

    source = SkinportSource(currency="EUR")
    source.get_price("AK-47 | Redline (Field-Tested)")

    assert len(recwarn) == 0
