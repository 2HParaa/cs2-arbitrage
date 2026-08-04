import time
import warnings
from decimal import Decimal
from functools import cache

import requests

from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price, PriceSource

CS2_APP_ID = 730
ITEMS_URL = "https://api.skinport.com/v1/items"
SALES_HISTORY_URL = "https://api.skinport.com/v1/sales/history"

MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 10


class SkinportError(Exception):
    """Erreur lors de la récupération d'un prix sur Skinport."""


@cache
def fetch_items(currency: str = "EUR") -> list[dict]:
    """Catalogue complet Skinport (~25 000 items en un seul appel) —
    réutilisé par SkinportSource ci-dessous, par catalog.py pour la
    navigation Type/Arme/Skin, et par scanner.py pour le scan de
    catalogue. Mis en cache par devise pour la durée du process : ces
    trois appelants convergent tous vers "USD" (cf. main.py), donc un
    seul appel réseau total par exécution plutôt que 2-3.

    Repéré le 2026-08-03 : sans ce cache, catalog.py (navigation) et
    scanner.py (scan) rappelaient chacun cet endpoint dans la même
    exécution, déclenchant un 429 (jamais observé avant, contrairement à
    ce que suggérait le commentaire précédent). Retry avec backoff ajouté
    par cohérence avec sources/steam.py et sources/csmoney.py."""
    for attempt in range(MAX_ATTEMPTS):
        response = requests.get(
            ITEMS_URL,
            params={"app_id": CS2_APP_ID, "currency": currency},
            timeout=10,
        )
        if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            continue
        if response.status_code == 429:
            raise SkinportError(
                f"Skinport limite les requêtes (429) pour le catalogue, même après "
                f"{MAX_ATTEMPTS} tentatives"
            )
        response.raise_for_status()
        return response.json()


@cache
def fetch_sales_history() -> list[dict]:
    """Historique de ventes complet Skinport (~36 000 items en un seul
    appel, vérifié en réel le 2026-08-04). Contrairement à fetch_items
    ("quantity" = offres actives), cet endpoint donne le nombre de VENTES
    RÉELLEMENT CONCLUES sur 24h/7j/30j/90j par item — c'est la seule
    plateforme du projet, avec Steam, à exposer un vrai signal de
    liquidité, mais la seule à le faire en masse (Steam est throttlé,
    un appel par item). Sert de proxy de liquidité cross-plateforme dans
    le rapport top 10 (gui.py) : peu importe la plateforme réelle du
    trade, si Skinport ne voit quasiment aucune vente sur l'item, le
    marché entier dessus est probablement mort. Pas de paramètre currency
    : seuls les compteurs "volume" sont exploités ici, jamais les prix
    associés (qui eux dépendent de la devise)."""
    for attempt in range(MAX_ATTEMPTS):
        response = requests.get(
            SALES_HISTORY_URL,
            params={"app_id": CS2_APP_ID},
            timeout=30,
        )
        if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            continue
        if response.status_code == 429:
            raise SkinportError(
                f"Skinport limite les requêtes (429) pour l'historique de ventes, "
                f"même après {MAX_ATTEMPTS} tentatives"
            )
        response.raise_for_status()
        return response.json()


def fetch_recent_sales_volume() -> dict[str, int]:
    """market_hash_name -> nombre de ventes conclues sur les 7 derniers
    jours. Fenêtre 7 jours plutôt que 24h (aussi disponible dans la même
    réponse) : moins bruitée pour distinguer un item vraiment illiquide
    d'un item juste calme la veille (choix utilisateur, 2026-08-04)."""
    return {
        item["market_hash_name"]: item["last_7_days"]["volume"]
        for item in fetch_sales_history()
    }


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
        if item.get("min_price") is None:
            raise SkinportError(f"Aucune offre de vente active sur Skinport pour '{item_name}'")

        # "quantity" = nombre d'offres actives, contrairement au "volume"
        # (ventes/24h) de Steam. En dessous du seuil, le prix repose sur trop
        # peu d'offres pour être fiable.
        quantity = item.get("quantity")
        if quantity is not None and int(quantity) < MIN_VOLUME_FOR_CONFIDENCE:
            warnings.warn(
                f"Peu d'offres actives sur Skinport pour '{item_name}' ({quantity} offres, "
                f"seuil de confiance : {MIN_VOLUME_FOR_CONFIDENCE}) — prix potentiellement peu fiable"
            )

        amount = Decimal(str(item["min_price"]))
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _get_catalog(self) -> dict:
        # L'API Skinport ne permet pas de chercher un item précis : elle
        # renvoie tout le catalogue en un seul appel. On le récupère une
        # seule fois par instance et on le réutilise pour les appels suivants.
        if self._catalog is None:
            items = fetch_items(self._currency)
            self._catalog = {item["market_hash_name"]: item for item in items}
        return self._catalog
