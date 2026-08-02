import warnings
from decimal import Decimal

import requests

from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price, PriceSource

CS2_GAME = "csgo"
PRICES_URL = "https://api.waxpeer.com/v1/prices"

# Endpoint public, aucune clé requise (vérifié en réel le 2026-08-02) : un
# seul appel renvoie tout le catalogue CS2 actuellement en vente (prix en
# centimes de USD, champ "min"), jamais rate-limité jusqu'ici. Le paramètre
# "currency" n'a aucun effet observé (montants identiques avec ou sans) :
# l'API est donc traitée comme USD-only ici plutôt que de risquer
# d'étiqueter silencieusement un montant USD comme EUR.
#
# Chaque item porte aussi une URL d'image directe ("img", .webp) : réutilisé
# par catalog.py pour les icônes, qui n'a donc plus besoin de résoudre
# chaque icône une par une via Steam (cf. sources/steam.py, throttlé).


class WaxpeerError(Exception):
    """Erreur lors de la récupération d'un prix sur Waxpeer."""


def fetch_items() -> list[dict]:
    """Catalogue complet Waxpeer (items actuellement en vente) en un seul
    appel — réutilisé par WaxpeerSource ci-dessous et par catalog.py pour
    les icônes."""
    response = requests.get(PRICES_URL, params={"game": CS2_GAME}, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise WaxpeerError("Waxpeer n'a pas renvoyé de catalogue exploitable")
    return data["items"]


class WaxpeerSource(PriceSource):
    def __init__(self, currency: str = "USD"):
        if currency != "USD":
            raise ValueError("WaxpeerSource ne supporte que USD (API sans conversion de devise)")
        self._currency = currency
        self._catalog = None

    @property
    def name(self) -> str:
        return "waxpeer"

    def get_price(self, item_name: str) -> Price:
        catalog = self._get_catalog()
        item = catalog.get(item_name)
        if item is None:
            raise WaxpeerError(f"Waxpeer n'a pas trouvé de prix pour '{item_name}'")

        # "count" = nombre d'offres actives, comme "quantity" sur Skinport.
        # En dessous du seuil, le prix repose sur trop peu d'offres pour
        # être fiable.
        count = item.get("count")
        if count is not None and int(count) < MIN_VOLUME_FOR_CONFIDENCE:
            warnings.warn(
                f"Peu d'offres actives sur Waxpeer pour '{item_name}' ({count} offres, "
                f"seuil de confiance : {MIN_VOLUME_FOR_CONFIDENCE}) — prix potentiellement peu fiable"
            )

        amount = Decimal(item["min"]) / 100
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _get_catalog(self) -> dict:
        # L'API Waxpeer ne permet pas de chercher un item précis : elle
        # renvoie tout le catalogue en un seul appel. On le récupère une
        # seule fois par instance et on le réutilise pour les appels suivants.
        if self._catalog is None:
            items = fetch_items()
            self._catalog = {item["name"]: item for item in items}
        return self._catalog
