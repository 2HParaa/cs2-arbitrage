from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import permutations

from cs2_arbitrage.normalize import NormalizedPrice

# Plateformes dont le paiement à la vente n'est pas retirable en cash
# (Steam Wallet : utilisable uniquement pour racheter sur Steam).
NON_CASH_SOURCES = {"steam"}

# Un item acheté sur le Steam Community Market est bloqué au trade pendant
# 7 jours (règle Valve spécifique aux achats Market, contrairement à un
# achat via trade sur Skinport/CS.Money/Waxpeer/CS.Deals/White.market qui
# livre un item déjà tradable) : inutilisable comme jambe d'achat pour un
# arbitrage rapide entre plateformes, donc exclu plutôt que simplement
# signalé.
TRADE_LOCKED_BUY_SOURCES = {"steam"}

# Un profit relatif de plus de 100% (le prix de vente dépasse le double du
# prix d'achat) entre deux marketplaces liquides n'arrive jamais en
# pratique : quand on l'observe, c'est presque toujours un défaut de
# donnée côté source plutôt qu'une vraie opportunité. Repéré le 2026-08-03
# sur des graffiti Waxpeer reposant sur une seule offre isolée (count: 1)
# cotées à des dizaines de milliers de dollars, alors que leur prix Steam
# de référence (renvoyé par Waxpeer dans le même appel) était de quelques
# centimes — un listing fantaisiste, pas un vrai prix de marché. Exclu
# plutôt que simplement signalé, comme TRADE_LOCKED_BUY_SOURCES.
MAX_SANE_PROFIT_PERCENT = Decimal(100)


@dataclass(frozen=True)
class Opportunity:
    item_name: str
    currency: str
    buy_source: str
    sell_source: str
    buy_price: Decimal
    # Prix à afficher en listant l'item sur sell_source (prix de marché
    # actuel, avant frais) : c'est ce prix-là qu'il faut rentrer sur la
    # plateforme, pas sell_net_price.
    sell_gross_price: Decimal
    # Ce qui atterrit réellement dans le solde une fois vendu à
    # sell_gross_price : les frais de sell_source sont déjà déduits ici,
    # pas à ajouter par-dessus par l'utilisateur.
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
            if buy.source in TRADE_LOCKED_BUY_SOURCES:
                continue
            if buy.currency != sell.currency:
                raise ValueError(
                    f"Devises différentes pour '{buy.item_name}': {buy.currency} vs {sell.currency}"
                )
            profit = sell.net_amount - buy.gross_amount
            if profit / buy.gross_amount * 100 > MAX_SANE_PROFIT_PERCENT:
                continue
            opportunities.append(
                Opportunity(
                    item_name=buy.item_name,
                    currency=buy.currency,
                    buy_source=buy.source,
                    sell_source=sell.source,
                    buy_price=buy.gross_amount,
                    sell_gross_price=sell.gross_amount,
                    sell_net_price=sell.net_amount,
                    profit=profit,
                    cash_realizable=sell.source not in NON_CASH_SOURCES,
                )
            )
    return opportunities


def profit_percent(opportunity: Opportunity) -> Decimal:
    """Profit rapporté au prix d'achat (retour sur investissement), en %.
    Sert à comparer des opportunités sur des items de prix très différents
    entre eux : un profit de 5 $ sur un item à 10 $ (+50%) est plus
    intéressant qu'un profit de 5 $ sur un item à 500 $ (+1%), alors que le
    profit en valeur absolue est identique."""
    return opportunity.profit / opportunity.buy_price * 100
