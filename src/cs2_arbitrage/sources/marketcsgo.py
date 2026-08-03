import warnings
from decimal import Decimal

import requests

from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price, PriceSource

PRICES_URL = "https://market.csgo.com/api/v2/prices/USD.json"

# Endpoint public, aucune clé requise (vérifié en réel le 2026-08-03) : un
# seul appel renvoie tout le catalogue (~27 300 items), directement en USD
# (pas de centimes/millièmes à convertir — vérifié par comparaison avec le
# vrai prix Steam : ex. AK-47 | Redline (Field-Tested) à 31,08 $ ici contre
# ~31,01 $ (médiane Steam), quasi identique, contrairement aux autres
# sources tierces qui tournent plutôt à 70-75% du prix Steam). Frais
# vendeur 5% (SteamAnalyst, cohérent avec la majorité des sources
# consultées ; une minorité annonce 2%, non retenue faute de confirmation).
#
# Chaque item ne porte que "market_hash_name", "price" et "volume" — pas
# d'enveloppe de succès ni de champ "count"/"quantity" nommé comme sur les
# autres sources. "volume" est traité comme le nombre d'offres actives
# (même rôle que "count" sur Waxpeer/"market_product_count" sur
# White.market) : aucun item du catalogue n'a de volume à 0, cohérent avec
# "présent seulement s'il y a une offre active" plutôt qu'un compteur de
# ventes historiques qui pourrait rester à 0 pour un item actuellement
# indisponible.


class MarketCSGOError(Exception):
    """Erreur lors de la récupération d'un prix sur market.csgo.com."""


def fetch_items() -> list[dict]:
    """Catalogue complet market.csgo.com en un seul appel — réutilisé par
    MarketCSGOSource ci-dessous."""
    response = requests.get(PRICES_URL, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise MarketCSGOError("market.csgo.com n'a pas renvoyé de catalogue exploitable")
    return data["items"]


class MarketCSGOSource(PriceSource):
    def __init__(self, currency: str = "USD"):
        if currency != "USD":
            raise ValueError("MarketCSGOSource ne supporte que USD (API sans conversion de devise)")
        self._currency = currency
        self._catalog = None

    @property
    def name(self) -> str:
        return "marketcsgo"

    def get_price(self, item_name: str) -> Price:
        catalog = self._get_catalog()
        item = catalog.get(item_name)
        if item is None:
            raise MarketCSGOError(f"market.csgo.com n'a pas trouvé de prix pour '{item_name}'")

        volume = item.get("volume")
        if volume is not None and int(volume) < MIN_VOLUME_FOR_CONFIDENCE:
            warnings.warn(
                f"Peu d'offres actives sur market.csgo.com pour '{item_name}' ({volume} offres, "
                f"seuil de confiance : {MIN_VOLUME_FOR_CONFIDENCE}) — prix potentiellement peu fiable"
            )

        amount = Decimal(item["price"])
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _get_catalog(self) -> dict:
        # L'API market.csgo.com ne permet pas de chercher un item précis :
        # elle renvoie tout le catalogue en un seul appel. On le récupère
        # une seule fois par instance et on le réutilise pour les appels
        # suivants.
        if self._catalog is None:
            items = fetch_items()
            self._catalog = {item["market_hash_name"]: item for item in items}
        return self._catalog
