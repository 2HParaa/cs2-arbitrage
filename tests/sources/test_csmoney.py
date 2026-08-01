import json
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from cs2_arbitrage.sources.csmoney import CSMoneyError, CSMoneySource


@pytest.fixture(autouse=True)
def mock_sleep(monkeypatch):
    # Le throttling proactif (time.sleep(THROTTLE_SECONDS) avant chaque
    # requête) ralentirait chaque test de plusieurs secondes si on ne le
    # mockait pas ici, une bonne fois pour tous les tests du fichier.
    mock = MagicMock()
    monkeypatch.setattr("cs2_arbitrage.sources.csmoney.time.sleep", mock)
    return mock


def _page_html(item: dict) -> str:
    page_params = json.dumps({"data": {"itemDetails": {"item": item}}})
    return f'<html><body><script id="__page-params">{page_params}</script></body></html>'


def _mock_get(item=None, status_code=200, body=None):
    response = Mock()
    response.status_code = status_code
    response.raise_for_status = Mock()
    response.text = body if body is not None else _page_html(item or {})
    return response


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_parses_price(mock_get):
    mock_get.return_value = _mock_get(
        {"fullName": "AK-47 | Redline (Field-Tested)", "minPrice": 30.99, "offerCount": 841}
    )

    source = CSMoneySource(currency="EUR")
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.item_name == "AK-47 | Redline (Field-Tested)"
    assert price.amount == Decimal("30.99")
    assert price.currency == "EUR"
    assert price.source == "csmoney"

    args, _ = mock_get.call_args
    assert args[0] == "https://cs.money/fr/csgo/ak-47-redline-field-tested/"


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_forces_utf8_encoding(mock_get):
    # CS.Money ne déclare pas de charset dans son Content-Type, donc
    # requests retombe sur ISO-8859-1 par défaut et corrompt les caractères
    # comme "★" ou "™" si on ne force pas l'encodage explicitement.
    response = _mock_get(
        {"fullName": "★ Karambit | Doppler (Factory New)", "minPrice": 1853.30, "offerCount": None}
    )
    mock_get.return_value = response

    source = CSMoneySource(currency="EUR")
    source.get_price("★ Karambit | Doppler (Factory New)")

    assert response.encoding == "utf-8"


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_builds_stattrak_slug(mock_get):
    mock_get.return_value = _mock_get(
        {
            "fullName": "StatTrak™ AK-47 | Redline (Field-Tested)",
            "minPrice": 66.31,
            "offerCount": 159,
        }
    )

    source = CSMoneySource(currency="EUR")
    source.get_price("StatTrak™ AK-47 | Redline (Field-Tested)")

    args, _ = mock_get.call_args
    assert args[0] == "https://cs.money/fr/csgo/stattrak-ak-47-redline-field-tested/"


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_builds_star_prefixed_slug(mock_get):
    mock_get.return_value = _mock_get(
        {"fullName": "★ Karambit | Doppler (Factory New)", "minPrice": 1853.30, "offerCount": None}
    )

    source = CSMoneySource(currency="EUR")
    source.get_price("★ Karambit | Doppler (Factory New)")

    args, _ = mock_get.call_args
    assert args[0] == "https://cs.money/fr/csgo/karambit-doppler-factory-new/"


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_builds_case_slug(mock_get):
    mock_get.return_value = _mock_get(
        {"fullName": "Shadow Case", "minPrice": 1.79, "offerCount": 345}
    )

    source = CSMoneySource(currency="EUR")
    source.get_price("Shadow Case")

    args, _ = mock_get.call_args
    assert args[0] == "https://cs.money/fr/csgo/shadow-case/"


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_raises_when_slug_not_found(mock_get):
    mock_get.return_value = _mock_get(status_code=404, body="<html>not found</html>")

    source = CSMoneySource()

    with pytest.raises(CSMoneyError, match="n'a pas trouvé de prix"):
        source.get_price("Item inexistant")


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_raises_when_no_active_listing(mock_get):
    mock_get.return_value = _mock_get(
        {"fullName": "Glock-18 | Fade (Factory New)", "minPrice": None, "offerCount": None}
    )

    source = CSMoneySource()

    with pytest.raises(CSMoneyError, match="Aucune offre de vente active"):
        source.get_price("Glock-18 | Fade (Factory New)")


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_raises_when_returned_item_does_not_match(mock_get):
    # Le slug deviné a résolu vers un item différent : on ne doit jamais
    # comparer silencieusement le mauvais prix.
    mock_get.return_value = _mock_get(
        {"fullName": "AK-47 | Vulcan (Field-Tested)", "minPrice": 15.0, "offerCount": 100}
    )

    source = CSMoneySource()

    with pytest.raises(CSMoneyError, match="renvoyé un item différent"):
        source.get_price("AK-47 | Redline (Field-Tested)")


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_raises_when_page_params_missing(mock_get):
    mock_get.return_value = _mock_get(body="<html><body>rien ici</body></html>")

    source = CSMoneySource()

    with pytest.raises(CSMoneyError, match="Impossible de lire les données"):
        source.get_price("AK-47 | Redline (Field-Tested)")


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_retries_on_429_then_succeeds(mock_get, mock_sleep):
    mock_get.side_effect = [
        _mock_get(status_code=429, body=""),
        _mock_get(status_code=429, body=""),
        _mock_get(
            {"fullName": "AK-47 | Redline (Field-Tested)", "minPrice": 30.99, "offerCount": 841}
        ),
    ]

    source = CSMoneySource(currency="EUR")
    price = source.get_price("AK-47 | Redline (Field-Tested)")

    assert price.amount == Decimal("30.99")
    assert mock_get.call_count == 3
    # 1 throttle par tentative (3) + 1 delai de retry apres chaque 429 (2)
    assert mock_sleep.call_count == 5


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_raises_after_exhausting_retries_on_429(mock_get):
    mock_get.return_value = _mock_get(status_code=429, body="")

    source = CSMoneySource()

    with pytest.raises(CSMoneyError, match="limite les requêtes"):
        source.get_price("AK-47 | Redline (Field-Tested)")

    assert mock_get.call_count == 4


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_warns_on_low_offer_count(mock_get):
    mock_get.return_value = _mock_get(
        {"fullName": "Desert Eagle | Blaze (Factory New)", "minPrice": 900.94, "offerCount": 1}
    )

    source = CSMoneySource(currency="EUR")

    with pytest.warns(UserWarning, match="Peu d'offres actives"):
        price = source.get_price("Desert Eagle | Blaze (Factory New)")

    assert price.amount == Decimal("900.94")


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_does_not_warn_on_sufficient_offer_count(mock_get, recwarn):
    mock_get.return_value = _mock_get(
        {"fullName": "AK-47 | Redline (Field-Tested)", "minPrice": 30.99, "offerCount": 841}
    )

    source = CSMoneySource(currency="EUR")
    source.get_price("AK-47 | Redline (Field-Tested)")

    assert len(recwarn) == 0


@patch("cs2_arbitrage.sources.csmoney.requests.get")
def test_get_price_does_not_warn_when_offer_count_is_none(mock_get, recwarn):
    # Certains items (ex: couteaux multi-phases) renvoient offerCount=null
    # sans que ça signifie une faible liquidité — vérifié en réel sur
    # "★ Karambit | Doppler (Factory New)".
    mock_get.return_value = _mock_get(
        {"fullName": "★ Karambit | Doppler (Factory New)", "minPrice": 1853.30, "offerCount": None}
    )

    source = CSMoneySource(currency="EUR")
    source.get_price("★ Karambit | Doppler (Factory New)")

    assert len(recwarn) == 0
