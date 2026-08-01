from decimal import Decimal

import requests

from cs2_arbitrage.sources.base import Price, PriceSource

CS2_APP_ID = 730
ITEMS_URL = "https://api.skinport.com/v1/items"


class SkinportError(Exception):
    """Erreur lors de la récupération d'un prix sur Skinport."""


class SkinportSource(PriceSource):
    def __init__(self, currency: str = "EUR"):
        self._currency = currency
        self._catalog = None

    @property
    def name(self) -> str:
        return "skinport"

    def get_price(self, item_name: str) -> Price:
        catalog = self._get_catalog()
        item = catalog.get(item_name)
        if item is None:
            raise SkinportError(f"Skinport n'a pas trouvé de prix pour '{item_name}'")

        amount = Decimal(str(item["min_price"]))
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _get_catalog(self) -> dict:
        # L'API Skinport ne permet pas de chercher un item precis : elle
        # renvoie tout le catalogue en un seul appel. On le recupere une
        # seule fois par instance et on le reutilise pour les appels suivants.
        if self._catalog is None:
            response = requests.get(
                ITEMS_URL,
                params={"app_id": CS2_APP_ID, "currency": self._currency},
                timeout=10,
            )
            response.raise_for_status()
            self._catalog = {item["market_hash_name"]: item for item in response.json()}
        return self._catalog
