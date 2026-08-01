from decimal import Decimal

import pytest

from cs2_arbitrage.compare import Opportunity, compare
from cs2_arbitrage.normalize import NormalizedPrice


def _price(item_name, source, gross_amount, net_amount, currency="EUR"):
    return NormalizedPrice(
        item_name=item_name,
        currency=currency,
        source=source,
        gross_amount=Decimal(gross_amount),
        net_amount=Decimal(net_amount),
    )


def test_compare_computes_profit_in_both_directions():
    prices = [
        _price("AK-47 | Redline", "cheap_market", "50.00", "45.00"),
        _price("AK-47 | Redline", "pricey_market", "70.00", "65.00"),
    ]

    opportunities = compare(prices)

    assert len(opportunities) == 2
    assert Opportunity(
        item_name="AK-47 | Redline",
        buy_source="cheap_market",
        sell_source="pricey_market",
        buy_price=Decimal("50.00"),
        sell_net_price=Decimal("65.00"),
        profit=Decimal("15.00"),
        cash_realizable=True,
    ) in opportunities
    assert Opportunity(
        item_name="AK-47 | Redline",
        buy_source="pricey_market",
        sell_source="cheap_market",
        buy_price=Decimal("70.00"),
        sell_net_price=Decimal("45.00"),
        profit=Decimal("-25.00"),
        cash_realizable=True,
    ) in opportunities


def test_compare_flags_steam_sale_as_not_cash_realizable():
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00"),
    ]

    opportunities = compare(prices)

    sell_on_steam = next(o for o in opportunities if o.sell_source == "steam")
    sell_on_skinport = next(o for o in opportunities if o.sell_source == "skinport")

    assert sell_on_steam.cash_realizable is False
    assert sell_on_skinport.cash_realizable is True


def test_compare_only_pairs_prices_of_the_same_item():
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00"),
        _price("AWP | Asiimov", "skinport", "100.00", "90.00"),
        _price("AWP | Asiimov", "steam", "120.00", "100.00"),
    ]

    opportunities = compare(prices)

    assert len(opportunities) == 4
    assert all(o.item_name in {"AK-47 | Redline", "AWP | Asiimov"} for o in opportunities)
    assert not any(o.item_name == "AK-47 | Redline" and "AWP" in o.buy_source for o in opportunities)


def test_compare_raises_on_currency_mismatch():
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00", currency="EUR"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00", currency="USD"),
    ]

    with pytest.raises(ValueError):
        compare(prices)
