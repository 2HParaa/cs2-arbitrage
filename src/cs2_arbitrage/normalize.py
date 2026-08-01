from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from cs2_arbitrage.sources.base import Price

CENT = Decimal("0.01")


def _additive_net(gross_amount: Decimal, fee_rate: Decimal) -> Decimal:
    # Steam calcule ses frais sur le montant que le vendeur recoit, puis les
    # ajoute pour obtenir le prix affiche (paye par l'acheteur) :
    #   prix affiche = recu + recu * frais = recu * (1 + frais)
    #   => recu = prix affiche / (1 + frais)
    return gross_amount / (1 + fee_rate)


def _subtractive_net(gross_amount: Decimal, fee_rate: Decimal) -> Decimal:
    # Skinport (et la plupart des marketplaces) deduisent les frais du prix
    # affiche, que l'acheteur paie integralement :
    #   recu = prix affiche * (1 - frais)
    return gross_amount * (1 - fee_rate)


# Taux et modele de frais vendeur standards, verifies au 2026-08-01
# (hors paliers/cas particuliers, phase 1) :
# - Steam : 15% (5% Valve + 10% frais du jeu), modele additif. L'argent recu
#   va dans le Steam Wallet, non retirable en cash.
# - Skinport : 8% en vente publique standard (6% des 1000 EUR/USD, 2% en
#   vente privee -- non geres pour l'instant), modele soustractif.
FEES = {
    "steam": (Decimal("0.15"), _additive_net),
    "skinport": (Decimal("0.08"), _subtractive_net),
}


@dataclass(frozen=True)
class NormalizedPrice:
    item_name: str
    currency: str
    source: str
    gross_amount: Decimal
    net_amount: Decimal


def normalize(price: Price) -> NormalizedPrice:
    fee_rate, net_fn = FEES[price.source]
    net_amount = net_fn(price.amount, fee_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    return NormalizedPrice(
        item_name=price.item_name,
        currency=price.currency,
        source=price.source,
        gross_amount=price.amount,
        net_amount=net_amount,
    )
