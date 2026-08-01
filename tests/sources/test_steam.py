from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from cs2_arbitrage.sources.steam import SteamMarketError, SteamMarketSource


@pytest.fixture(autouse=True)
def mock_sleep(monkeypatch):
    # Le throttling proactif (time.sleep(THROTTLE_SECONDS) avant chaque
    # requête) ralentirait chaque test de plusieurs secondes si on ne le
    # mockait pas ici, une bonne fois pour tous les tests du fichier.
    mock = MagicMock()
    monkeypatch.setattr("cs2_arbitrage.sources.steam.time.sleep", mock)
    return mock


def _mock_get(json_data, status_code=200):
    response = Mock()
    response.status_code = status_code
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

    with pytest.raises(SteamMarketError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_retries_on_429_then_succeeds(mock_get, mock_sleep):
    mock_get.side_effect = [
        _mock_get({}, status_code=429),
        _mock_get({}, status_code=429),
        _mock_get({"success": True, "lowest_price": "12,34€"}),
    ]

    source = SteamMarketSource(currency="EUR")
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.amount == Decimal("12.34")
    assert mock_get.call_count == 3
    # 1 throttle par tentative (3) + 1 delai de retry apres chaque 429 (2)
    assert mock_sleep.call_count == 5


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_raises_after_exhausting_retries_on_429(mock_get, mock_sleep):
    mock_get.return_value = _mock_get({}, status_code=429)

    source = SteamMarketSource()

    with pytest.raises(SteamMarketError):
        source.get_price("AK-47 | Redline (Field-Tested)")

    assert mock_get.call_count == 4


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_raises_when_no_active_listing(mock_get):
    # Steam répond "success: true" sans "lowest_price" quand il n'y a aucune
    # offre de vente active (cf. "Glock-18 | Fade (Factory New)" en réel).
    mock_get.return_value = _mock_get({"success": True})

    source = SteamMarketSource()

    with pytest.raises(SteamMarketError, match="Aucune offre de vente active"):
        source.get_price("Glock-18 | Fade (Factory New)")


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_warns_on_low_volume(mock_get):
    mock_get.return_value = _mock_get({"success": True, "lowest_price": "12,34€", "volume": "3"})

    source = SteamMarketSource(currency="EUR")

    with pytest.warns(UserWarning, match="Volume faible"):
        price = source.get_price("Desert Eagle | Blaze (Factory New)")

    assert price.amount == Decimal("12.34")


@patch("cs2_arbitrage.sources.steam.requests.get")
def test_get_price_does_not_warn_on_sufficient_volume(mock_get, recwarn):
    mock_get.return_value = _mock_get({"success": True, "lowest_price": "12,34€", "volume": "81"})

    source = SteamMarketSource(currency="EUR")
    source.get_price("AK-47 | Redline (Field-Tested)")

    assert len(recwarn) == 0
