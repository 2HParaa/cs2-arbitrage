from unittest.mock import Mock, patch

import pytest

from cs2_arbitrage import platform_links
from cs2_arbitrage.platform_links import build_item_url
from cs2_arbitrage.sources.skinport import fetch_items as fetch_skinport_items
from cs2_arbitrage.sources.waxpeer import fetch_items as fetch_waxpeer_items
from cs2_arbitrage.sources.whitemarket import fetch_items as fetch_whitemarket_items


@pytest.fixture(autouse=True)
def clear_caches():
    # Les fetch_items() sous-jacents (skinport/waxpeer/whitemarket) ET les
    # index dérivés de platform_links (_skinport_item_pages, etc.) sont
    # tous mis en cache pour la durée du process : sans ce nettoyage, un
    # test récupérerait les données mockées d'un test précédent.
    fetch_skinport_items.cache_clear()
    fetch_waxpeer_items.cache_clear()
    fetch_whitemarket_items.cache_clear()
    platform_links._skinport_item_pages.cache_clear()
    platform_links._whitemarket_links.cache_clear()
    platform_links._waxpeer_slugs.cache_clear()
    yield
    fetch_skinport_items.cache_clear()
    fetch_waxpeer_items.cache_clear()
    fetch_whitemarket_items.cache_clear()
    platform_links._skinport_item_pages.cache_clear()
    platform_links._whitemarket_links.cache_clear()
    platform_links._waxpeer_slugs.cache_clear()


def _mock_get(json_data):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = json_data
    return response


def test_build_item_url_returns_none_for_unknown_source():
    assert build_item_url("unknown", "AK-47 | Redline (Field-Tested)") is None


def test_build_item_url_steam_reconstructs_listing_url():
    url = build_item_url("steam", "AK-47 | Redline (Field-Tested)")

    assert url == (
        "https://steamcommunity.com/market/listings/730/AK-47%20%7C%20Redline%20%28Field-Tested%29"
    )


def test_build_item_url_csmoney_builds_slug_url():
    url = build_item_url("csmoney", "StatTrak™ AK-47 | Redline (Field-Tested)")

    assert url == "https://cs.money/en/csgo/stattrak-ak-47-redline-field-tested/"


def test_build_item_url_csdeals_is_a_best_effort_search_link():
    url = build_item_url("csdeals", "AK-47 | Redline (Field-Tested)")

    assert url.startswith("https://cs.deals/market/730?name=")
    assert "AK-47" in url


def test_build_item_url_marketcsgo_is_a_best_effort_search_link():
    url = build_item_url("marketcsgo", "AK-47 | Redline (Field-Tested)")

    assert url.startswith("https://market.csgo.com/en/?search=")


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_build_item_url_skinport_uses_item_page_field(mock_get):
    mock_get.return_value = _mock_get(
        [
            {
                "market_hash_name": "AK-47 | Redline (Field-Tested)",
                "item_page": "https://skinport.com/item/ak-47-redline-field-tested",
            }
        ]
    )

    url = build_item_url("skinport", "AK-47 | Redline (Field-Tested)")

    assert url == "https://skinport.com/item/ak-47-redline-field-tested"


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_build_item_url_skinport_returns_none_when_item_absent(mock_get):
    mock_get.return_value = _mock_get([])

    assert build_item_url("skinport", "Item inexistant") is None


@patch("cs2_arbitrage.sources.whitemarket.requests.get")
def test_build_item_url_whitemarket_uses_market_product_link_field(mock_get):
    mock_get.return_value = _mock_get(
        [
            {
                "market_hash_name": "AK-47 | Redline (Field-Tested)",
                "market_product_link": ("https://white.market/item?appId=730&nameHash=AK-47"),
            }
        ]
    )

    url = build_item_url("whitemarket", "AK-47 | Redline (Field-Tested)")

    assert url == "https://white.market/item?appId=730&nameHash=AK-47"


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_build_item_url_waxpeer_derives_slug_from_image_url(mock_get):
    mock_get.return_value = _mock_get(
        {
            "success": True,
            "items": [
                {
                    "name": "AK-47 | Redline (Field-Tested)",
                    "img": "https://images.waxpeer.com/i/730-ak-47-redline-field-tested.webp",
                }
            ],
        }
    )

    url = build_item_url("waxpeer", "AK-47 | Redline (Field-Tested)")

    assert url == "https://waxpeer.com/item/ak-47-redline-field-tested"


@patch("cs2_arbitrage.sources.waxpeer.requests.get")
def test_build_item_url_waxpeer_returns_none_when_no_image(mock_get):
    mock_get.return_value = _mock_get(
        {"success": True, "items": [{"name": "AK-47 | Redline (Field-Tested)"}]}
    )

    assert build_item_url("waxpeer", "AK-47 | Redline (Field-Tested)") is None


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_build_item_url_skinport_returns_none_on_network_error(mock_get):
    import requests

    mock_get.side_effect = requests.ConnectionError("boom")

    assert build_item_url("skinport", "AK-47 | Redline (Field-Tested)") is None
