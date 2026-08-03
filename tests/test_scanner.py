from decimal import Decimal
from unittest.mock import patch

from cs2_arbitrage.scanner import fetch_scan_prices, run_catalog_scan

SKINPORT_ITEMS = [
    {"market_hash_name": "Cheap Sticker", "min_price": 2.0, "quantity": 50},
    {"market_hash_name": "Expensive Knife", "min_price": 900.0, "quantity": 5},
    {"market_hash_name": "No Active Listing", "min_price": None, "quantity": 0},
]
WAXPEER_ITEMS = [
    {"name": "Cheap Sticker", "min": 1500, "count": 20},  # 1500/1000 = 1.50
    {"name": "Expensive Knife", "min": 950000, "count": 3},  # 950.00
    {"name": "Only On Waxpeer", "min": 500, "count": 10},  # 0.50, pas de prix Skinport
]
CSDEALS_ITEMS = [
    {"marketname": "Cheap Sticker", "lowest_price": "3.50"},
    {"marketname": "Only On Waxpeer", "lowest_price": "1.00"},
]
WHITEMARKET_ITEMS = []
MARKETCSGO_ITEMS = []


def _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo):
    mock_skinport.return_value = SKINPORT_ITEMS
    mock_waxpeer.return_value = WAXPEER_ITEMS
    mock_csdeals.return_value = CSDEALS_ITEMS
    mock_whitemarket.return_value = WHITEMARKET_ITEMS
    mock_marketcsgo.return_value = MARKETCSGO_ITEMS


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_skips_low_liquidity_skinport_reference_price(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    mock_skinport.return_value = [
        {"market_hash_name": "Thin Item", "min_price": 1.0, "quantity": 3},
    ]
    mock_waxpeer.return_value = []
    mock_csdeals.return_value = []
    mock_whitemarket.return_value = []
    mock_marketcsgo.return_value = []

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    assert prices == []


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_skips_low_liquidity_waxpeer_price_but_keeps_others(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    mock_skinport.return_value = [
        {"market_hash_name": "Item", "min_price": 1.0, "quantity": 50},
    ]
    mock_waxpeer.return_value = [
        {"name": "Item", "min": 2000, "count": 3},  # sous MIN_VOLUME_FOR_CONFIDENCE
    ]
    mock_csdeals.return_value = [
        {"marketname": "Item", "lowest_price": "1.80"},
    ]
    mock_whitemarket.return_value = []
    mock_marketcsgo.return_value = []

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    sources = {price.source for price in prices}
    assert sources == {"skinport", "csdeals"}


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_skips_low_liquidity_whitemarket_price_but_keeps_others(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    mock_skinport.return_value = [
        {"market_hash_name": "Item", "min_price": 1.0, "quantity": 50},
    ]
    mock_waxpeer.return_value = []
    mock_csdeals.return_value = []
    mock_whitemarket.return_value = [
        {"market_hash_name": "Item", "price": "1.90", "market_product_count": 3},
    ]
    mock_marketcsgo.return_value = []

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    sources = {price.source for price in prices}
    assert "whitemarket" not in sources


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_skips_low_liquidity_marketcsgo_price_but_keeps_others(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    mock_skinport.return_value = [
        {"market_hash_name": "Item", "min_price": 1.0, "quantity": 50},
    ]
    mock_waxpeer.return_value = []
    mock_csdeals.return_value = []
    mock_whitemarket.return_value = []
    mock_marketcsgo.return_value = [
        {"market_hash_name": "Item", "price": "1.95", "volume": "3"},
    ]

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    sources = {price.source for price in prices}
    assert "marketcsgo" not in sources


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_excludes_items_below_min_price(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    mock_skinport.return_value = [
        {"market_hash_name": "Two Cent Item", "min_price": 0.02, "quantity": 50},
        {"market_hash_name": "Cheap Sticker", "min_price": 2.0, "quantity": 50},
    ]
    mock_waxpeer.return_value = []
    mock_csdeals.return_value = []
    mock_whitemarket.return_value = []
    mock_marketcsgo.return_value = []

    prices = fetch_scan_prices(Decimal("0.5"), Decimal(5))

    names = {price.item_name for price in prices}
    assert "Two Cent Item" not in names
    assert "Cheap Sticker" in names


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_qualifies_items_by_skinport_price(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo)

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    names = {price.item_name for price in prices}
    assert names == {"Cheap Sticker"}


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_ignores_items_absent_from_skinport_even_if_cheap_elsewhere(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    # "Only On Waxpeer" est à 0.50 $/1.00 $ sur Waxpeer/CS.Deals mais absent
    # de Skinport (la référence) : ne doit jamais qualifier.
    _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo)

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    assert "Only On Waxpeer" not in {price.item_name for price in prices}


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_includes_all_sources_for_a_qualifying_item(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    mock_skinport.return_value = SKINPORT_ITEMS
    mock_waxpeer.return_value = WAXPEER_ITEMS
    mock_csdeals.return_value = CSDEALS_ITEMS
    mock_whitemarket.return_value = [
        {"market_hash_name": "Cheap Sticker", "price": "2.90", "market_product_count": 40},
    ]
    mock_marketcsgo.return_value = [
        {"market_hash_name": "Cheap Sticker", "price": "3.10", "volume": "60"},
    ]

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    sticker_prices = {p.source: p.amount for p in prices if p.item_name == "Cheap Sticker"}
    assert sticker_prices == {
        "skinport": Decimal("2.0"),
        "waxpeer": Decimal("1.5"),
        "csdeals": Decimal("3.50"),
        "whitemarket": Decimal("2.90"),
        "marketcsgo": Decimal("3.10"),
    }


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_excludes_items_above_threshold_on_skinport(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo)

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    assert "Expensive Knife" not in {price.item_name for price in prices}


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_fetch_scan_prices_skips_items_without_active_skinport_listing(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo)

    prices = fetch_scan_prices(Decimal(0), Decimal(5))

    assert "No Active Listing" not in {price.item_name for price in prices}


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_run_catalog_scan_only_returns_profitable_opportunities(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo)

    opportunities = run_catalog_scan(Decimal(0), Decimal(5))

    assert all(opportunity.profit > 0 for opportunity in opportunities)
    assert all(opportunity.item_name == "Cheap Sticker" for opportunity in opportunities)


@patch("cs2_arbitrage.scanner.fetch_marketcsgo_items")
@patch("cs2_arbitrage.scanner.fetch_whitemarket_items")
@patch("cs2_arbitrage.scanner.fetch_csdeals_items")
@patch("cs2_arbitrage.scanner.fetch_waxpeer_items")
@patch("cs2_arbitrage.scanner.fetch_skinport_items")
def test_run_catalog_scan_best_opportunity_buys_on_skinport_sells_on_csdeals(
    mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo
):
    # waxpeer(1.50) -> csdeals(net 3.43) serait le meilleur en valeur
    # absolue (+1.93, +129%), mais dépasse le seuil de sanité à 100%
    # (compare.MAX_SANE_PROFIT_PERCENT) et est donc exclu : le meilleur
    # restant est skinport(2.00) -> csdeals(net 3.43), +71.5%.
    _mock_all(mock_skinport, mock_waxpeer, mock_csdeals, mock_whitemarket, mock_marketcsgo)

    opportunities = run_catalog_scan(Decimal(0), Decimal(5))

    best = max(opportunities, key=lambda o: o.profit)
    assert best.buy_source == "skinport"
    assert best.sell_source == "csdeals"
