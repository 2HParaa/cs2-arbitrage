from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import permutations

from cs2_arbitrage.normalize import NormalizedPrice

# Plateformes dont le paiement à la vente n'est pas retirable en cash
# (Steam Wallet : utilisable uniquement pour racheter sur Steam).
NON_CASH_SOURCES = {"steam"}


@dataclass(frozen=True)
class Opportunity:
    item_name: str
    buy_source: str
    sell_source: str
    buy_price: Decimal
    sell_net_price: Decimal
    profit: Decimal
    cash_realizable: bool


def compare(prices: list[NormalizedPrice]) -> list[Opportunity]:
    by_item = defaultdict(list)
    for price in prices:
        by_item[price.item_name].append(price)

    opportunities = []
    for item_prices in by_item.values():
        for buy, sell in permutations(item_prices, 2):
            if buy.source == sell.source:
                continue
            if buy.currency != sell.currency:
                raise ValueError(
                    f"Devises différentes pour '{buy.item_name}': {buy.currency} vs {sell.currency}"
                )
            opportunities.append(
                Opportunity(
                    item_name=buy.item_name,
                    buy_source=buy.source,
                    sell_source=sell.source,
                    buy_price=buy.gross_amount,
                    sell_net_price=sell.net_amount,
                    profit=sell.net_amount - buy.gross_amount,
                    cash_realizable=sell.source not in NON_CASH_SOURCES,
                )
            )
    return opportunities
