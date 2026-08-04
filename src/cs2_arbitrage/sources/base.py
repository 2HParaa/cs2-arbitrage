from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

# Seuil minimum de liquidité (nombre d'OFFRES ACTIVES, pas de ventes) en
# dessous duquel un prix est considéré peu fiable statistiquement. Pas de
# valeur "scientifiquement correcte" ici : compromis fiabilité/couverture
# choisi par l'utilisateur. Partagé par Skinport/CS.Money/Waxpeer/
# White.market/market.csgo.com (leur champ "quantity"/"offerCount"/
# "count"/"market_product_count"/"volume" mesure tous la même chose :
# combien d'offres sont affichées MAINTENANT, pas combien se sont vendues)
# et par scanner.py comme garde-fou anti-données-aberrantes lors d'un scan
# (repéré le 2026-08-03 : des graffiti Waxpeer à une seule offre isolée
# cotés à des dizaines de milliers de dollars). Volontairement PAS utilisé
# pour Steam, dont le champ "volume" est un vrai nombre de ventes conclues
# (cf. MIN_SALES_VOLUME_FOR_CONFIDENCE ci-dessous) : une offre active et
# une vente conclue ne sont pas la même grandeur, ça n'aurait pas de sens
# de les comparer au même seuil numérique.
MIN_VOLUME_FOR_CONFIDENCE = 10

# Seuil minimum de VENTES RÉELLEMENT CONCLUES récentes, pour les sources
# qui exposent cette donnée (contrairement à MIN_VOLUME_FOR_CONFIDENCE
# ci-dessus, qui ne compte que des offres actives). Aujourd'hui utilisé
# uniquement par Steam (son champ "volume" = ventes/24h, cf. sources/
# steam.py). Calibré le 2026-08-04 pour rester cohérent avec le seuil du
# filtre de liquidité du rapport top 10 (LIQUIDITY_SLIDER_DEFAULT, gui.py,
# 14 ventes/7 jours) : 14 / 7 = 2 ventes/jour. Avant ce calibrage, Steam
# utilisait MIN_VOLUME_FOR_CONFIDENCE (10, donc 10 ventes/24h) — un seuil
# ~5x plus strict que celui qu'on utilise par ailleurs comme référence de
# liquidité "acceptable", sans raison d'être aussi sévère spécifiquement
# sur Steam.
MIN_SALES_VOLUME_FOR_CONFIDENCE = 2


@dataclass(frozen=True)
class Price:
    item_name: str
    amount: Decimal
    currency: str
    source: str


class PriceSource(ABC):
    """Interface commune à toutes les marketplaces (pattern adapter)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nom de la marketplace, ex: 'steam', 'skinport'."""

    @abstractmethod
    def get_price(self, item_name: str) -> Price:
        """Récupère le prix courant d'un item sur cette marketplace."""
