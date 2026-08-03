from decimal import Decimal

from cs2_arbitrage.compare import Opportunity
from cs2_arbitrage.report import generate_report


def _opportunity(
    item_name,
    buy_source,
    sell_source,
    buy_price,
    sell_net_price,
    profit,
    currency="EUR",
    cash_realizable=True,
    sell_gross_price=None,
):
    return Opportunity(
        item_name=item_name,
        currency=currency,
        buy_source=buy_source,
        sell_source=sell_source,
        buy_price=Decimal(buy_price),
        # Valeur brute non pertinente pour ces tests (texte/tri) : par
        # défaut, on réutilise le net plutôt que d'inventer une vraie
        # relation frais/brut ici.
        sell_gross_price=Decimal(sell_gross_price) if sell_gross_price else Decimal(sell_net_price),
        sell_net_price=Decimal(sell_net_price),
        profit=Decimal(profit),
        cash_realizable=cash_realizable,
    )


def test_report_lists_profitable_opportunities_sorted_by_profit():
    opportunities = [
        _opportunity("AK-47 | Redline", "cheap_market", "pricey_market", "50.00", "60.00", "10.00"),
        _opportunity("AK-47 | Redline", "other_market", "pricey_market", "50.00", "70.00", "20.00"),
    ]

    report = generate_report(opportunities)

    lines = report.splitlines()
    best_index = next(i for i, line in enumerate(lines) if "other_market" in line)
    worst_index = next(
        i for i, line in enumerate(lines) if "cheap_market" in line and "pricey" in line
    )
    assert best_index < worst_index


def test_report_sorts_by_relative_profit_not_absolute_amount():
    opportunities = [
        # +50 $ sur un item à 1000 $ : +5%
        _opportunity("Knife", "cheap_pct", "market", "1000.00", "1050.00", "50.00"),
        # +10 $ sur un item à 20 $ : +50%, moins de profit en valeur absolue
        # mais bien plus intéressant en relatif.
        _opportunity("Knife", "best_pct", "market", "20.00", "30.00", "10.00"),
    ]

    report = generate_report(opportunities)

    lines = report.splitlines()
    best_index = next(i for i, line in enumerate(lines) if "best_pct" in line)
    worst_index = next(i for i, line in enumerate(lines) if "cheap_pct" in line)
    assert best_index < worst_index


def test_report_excludes_unprofitable_opportunities():
    opportunities = [
        _opportunity("AK-47 | Redline", "market_a", "market_b", "70.00", "60.00", "-10.00"),
    ]

    report = generate_report(opportunities)

    assert "Aucune opportunité rentable." in report
    assert "market_a" not in report


def test_report_flags_steam_wallet_opportunities():
    opportunities = [
        _opportunity(
            "AK-47 | Redline", "skinport", "steam", "50.00", "60.00", "10.00", cash_realizable=False
        ),
    ]

    report = generate_report(opportunities)

    assert "Steam Wallet" in report


def test_report_does_not_flag_cash_realizable_opportunities():
    opportunities = [
        _opportunity("AK-47 | Redline", "steam", "skinport", "50.00", "60.00", "10.00"),
    ]

    report = generate_report(opportunities)

    assert "Steam Wallet" not in report
