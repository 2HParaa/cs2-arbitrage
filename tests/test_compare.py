from decimal import Decimal

import pytest

from cs2_arbitrage.compare import Opportunity, compare, profit_percent
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
    assert (
        Opportunity(
            item_name="AK-47 | Redline",
            currency="EUR",
            buy_source="cheap_market",
            sell_source="pricey_market",
            buy_price=Decimal("50.00"),
            sell_gross_price=Decimal("70.00"),
            sell_net_price=Decimal("65.00"),
            profit=Decimal("15.00"),
            cash_realizable=True,
        )
        in opportunities
    )
    assert (
        Opportunity(
            item_name="AK-47 | Redline",
            currency="EUR",
            buy_source="pricey_market",
            sell_source="cheap_market",
            buy_price=Decimal("70.00"),
            sell_gross_price=Decimal("50.00"),
            sell_net_price=Decimal("45.00"),
            profit=Decimal("-25.00"),
            cash_realizable=True,
        )
        in opportunities
    )


def test_compare_flags_steam_sale_as_not_cash_realizable():
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00"),
    ]

    opportunities = compare(prices)

    sell_on_steam = next(o for o in opportunities if o.sell_source == "steam")

    assert sell_on_steam.cash_realizable is False


def test_compare_excludes_steam_as_buy_leg():
    # Un item acheté sur le Steam Market est bloqué au trade 7 jours : ce
    # n'est pas une jambe d'achat utilisable pour un arbitrage rapide.
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00"),
    ]

    opportunities = compare(prices)

    assert not any(o.buy_source == "steam" for o in opportunities)
    assert len(opportunities) == 1
    assert opportunities[0].buy_source == "skinport"
    assert opportunities[0].sell_source == "steam"


def test_compare_only_pairs_prices_of_the_same_item():
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00"),
        _price("AWP | Asiimov", "skinport", "100.00", "90.00"),
        _price("AWP | Asiimov", "steam", "120.00", "100.00"),
    ]

    opportunities = compare(prices)

    # Steam exclu comme jambe d'achat (cf. test_compare_excludes_steam_as_buy_leg) :
    # 1 seule direction valide par item plutôt que 2.
    assert len(opportunities) == 2
    assert all(o.item_name in {"AK-47 | Redline", "AWP | Asiimov"} for o in opportunities)
    assert not any(
        o.item_name == "AK-47 | Redline" and "AWP" in o.buy_source for o in opportunities
    )


def test_compare_excludes_opportunities_over_100_percent_profit():
    # Repéré en réel sur des graffiti Waxpeer à une seule offre isolée,
    # cotées à des dizaines de milliers de dollars alors que leur vrai prix
    # est de quelques centimes : un profit relatif de plus de 100% signale
    # presque toujours un défaut de donnée, pas une vraie opportunité.
    prices = [
        _price("Sealed Graffiti | Question Mark", "skinport", "0.20", "0.18"),
        _price("Sealed Graffiti | Question Mark", "waxpeer", "90322.46", "85806.34"),
    ]

    opportunities = compare(prices)

    # La direction absurde (acheter pas cher, "vendre" 450x plus cher) est
    # exclue ; l'autre sens (perte, en dessous du seuil) reste, comme pour
    # n'importe quelle paire de prix normale.
    assert not any(o.buy_source == "skinport" for o in opportunities)
    assert any(o.buy_source == "waxpeer" and o.profit < 0 for o in opportunities)


def test_compare_keeps_opportunities_at_exactly_100_percent_profit():
    prices = [
        _price("Item", "skinport", "10.00", "9.00"),
        _price("Item", "waxpeer", "20.00", "20.00"),  # net = 2x buy_price pile
    ]

    opportunities = compare(prices)

    buy_skinport = next(o for o in opportunities if o.buy_source == "skinport")
    assert buy_skinport.profit == Decimal("10.00")


def test_compare_raises_on_currency_mismatch():
    prices = [
        _price("AK-47 | Redline", "skinport", "50.00", "45.00", currency="EUR"),
        _price("AK-47 | Redline", "steam", "70.00", "60.00", currency="USD"),
    ]

    with pytest.raises(ValueError):
        compare(prices)


def test_profit_percent_is_profit_relative_to_buy_price():
    opportunity = Opportunity(
        item_name="AK-47 | Redline",
        currency="EUR",
        buy_source="skinport",
        sell_source="steam",
        buy_price=Decimal("20.00"),
        sell_gross_price=Decimal("32.00"),
        sell_net_price=Decimal("30.00"),
        profit=Decimal("10.00"),
        cash_realizable=True,
    )

    assert profit_percent(opportunity) == Decimal("50.00")


def test_profit_percent_ranks_a_smaller_absolute_profit_higher_when_more_relatively_profitable():
    small_but_relatively_better = Opportunity(
        item_name="Item",
        currency="EUR",
        buy_source="a",
        sell_source="b",
        buy_price=Decimal("20.00"),
        sell_gross_price=Decimal("32.00"),
        sell_net_price=Decimal("30.00"),
        profit=Decimal("10.00"),  # +50%
        cash_realizable=True,
    )
    large_but_relatively_worse = Opportunity(
        item_name="Item",
        currency="EUR",
        buy_source="a",
        sell_source="b",
        buy_price=Decimal("1000.00"),
        sell_gross_price=Decimal("1120.00"),
        sell_net_price=Decimal("1050.00"),
        profit=Decimal("50.00"),  # +5%
        cash_realizable=True,
    )

    assert profit_percent(small_but_relatively_better) > profit_percent(large_but_relatively_worse)
