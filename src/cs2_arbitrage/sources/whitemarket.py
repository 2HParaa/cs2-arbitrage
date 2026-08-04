import warnings
from decimal import Decimal
from functools import cache

import requests

from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price, PriceSource

CS2_APP_ID = 730
PRICES_URL = f"https://s3.white.market/export/v1/prices/{CS2_APP_ID}.json"

# Endpoint public, aucune clé requise (vérifié en réel le 2026-08-03) : un
# seul appel renvoie tout le catalogue (~21 000 items), directement en
# tableau JSON (pas d'enveloppe {"success": ..., "response": {...}} comme
# CS.Deals). Prix ("price") déjà en dollars bruts (pas de centimes/
# millièmes à convertir, vérifié par comparaison avec le vrai prix Steam :
# ex. AK-47 | Redline (Field-Tested) à 30,69 $ ici contre 41,83 $ sur
# Steam, ~73%, cohérent pour une marketplace tierce). Frais vendeur 5%,
# pas de frais acheteur.


class WhiteMarketError(Exception):
    """Erreur lors de la récupération d'un prix sur White.market."""


@cache
def fetch_items() -> list[dict]:
    """Catalogue complet White.market en un seul appel — réutilisé par
    WhiteMarketSource ci-dessous et par platform_links.py pour les liens
    directs vers les items (market_product_link). Mis en cache pour la
    durée du process (comme sources/skinport.py) : pas question de
    retélécharger tout le catalogue à chaque appelant."""
    response = requests.get(PRICES_URL, timeout=10)
    response.raise_for_status()
    return response.json()


class WhiteMarketSource(PriceSource):
    def __init__(self, currency: str = "USD"):
        if currency != "USD":
            raise ValueError(
                "WhiteMarketSource ne supporte que USD (API sans conversion de devise)"
            )
        self._currency = currency
        self._catalog = None

    @property
    def name(self) -> str:
        return "whitemarket"

    def get_price(self, item_name: str) -> Price:
        catalog = self._get_catalog()
        item = catalog.get(item_name)
        if item is None:
            raise WhiteMarketError(f"White.market n'a pas trouvé de prix pour '{item_name}'")

        # "market_product_count" = nombre d'offres actives, comme "count"
        # sur Waxpeer. En dessous du seuil, le prix repose sur trop peu
        # d'offres pour être fiable.
        count = item.get("market_product_count")
        if count is not None and int(count) < MIN_VOLUME_FOR_CONFIDENCE:
            warnings.warn(
                f"Peu d'offres actives sur White.market pour '{item_name}' ({count} offres, "
                f"seuil de confiance : {MIN_VOLUME_FOR_CONFIDENCE}) — prix potentiellement peu fiable"
            )

        amount = Decimal(item["price"])
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _get_catalog(self) -> dict:
        # L'API White.market ne permet pas de chercher un item précis :
        # elle renvoie tout le catalogue en un seul appel. On le récupère
        # une seule fois par instance et on le réutilise pour les appels
        # suivants.
        if self._catalog is None:
            items = fetch_items()
            self._catalog = {item["market_hash_name"]: item for item in items}
        return self._catalog
