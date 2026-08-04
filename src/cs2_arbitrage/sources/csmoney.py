import json
import re
import time
import warnings
from decimal import Decimal

import requests

from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price, PriceSource

BASE_URL = "https://cs.money"
LOCALES = {"EUR": "fr", "USD": "en"}

# CS.Money n'a pas d'API publique documentée (cf. CLAUDE.md, phase 2). Le
# prix est embarqué dans le HTML de la page item (rendu côté serveur en
# Next.js), dans un <script id="__page-params">. Aucune limite de débit
# n'est documentée : testé manuellement sans blocage jusqu'à 0.375s entre
# requêtes (2026-08-02), 0.7s gardé en prod pour une marge de sécurité.
PAGE_PARAMS_PATTERN = re.compile(r'<script id="__page-params"[^>]*>(.*?)</script>', re.DOTALL)
THROTTLE_SECONDS = 0.7
MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 10


class CSMoneyError(Exception):
    """Erreur lors de la récupération d'un prix sur CS.Money."""


def build_slug(item_name: str) -> str:
    # Ex: "StatTrak™ AK-47 | Redline (Field-Tested)"
    #     -> "stattrak-ak-47-redline-field-tested"
    #     "★ Karambit | Doppler (Factory New)"
    #     -> "karambit-doppler-factory-new"
    # Vérifié en réel contre le vrai catalogue CS.Money (armes, couteaux
    # StatTrak/★, caisses). Fonction autonome (pas une méthode) : réutilisée
    # telle quelle par platform_links.py pour construire un lien cliquable,
    # sans dépendre d'une instance CSMoneySource.
    name = item_name
    is_stattrak = name.startswith("StatTrak™ ")
    if is_stattrak:
        name = name[len("StatTrak™ ") :]
    name = name.replace("★ ", "")
    name = re.sub(r"[|()]", " ", name)
    slug = "-".join(name.lower().split())
    return f"stattrak-{slug}" if is_stattrak else slug


class CSMoneySource(PriceSource):
    def __init__(self, currency: str = "EUR"):
        self._currency = currency
        self._locale = LOCALES[currency]

    @property
    def name(self) -> str:
        return "csmoney"

    def get_price(self, item_name: str) -> Price:
        slug = self._to_slug(item_name)
        html = self._fetch(slug)
        item = self._parse_item(html, item_name)

        # "offerCount" = nombre d'offres actives, comme "quantity" sur
        # Skinport. En dessous du seuil, le prix repose sur trop peu
        # d'offres pour être fiable.
        offer_count = item.get("offerCount")
        if offer_count is not None and int(offer_count) < MIN_VOLUME_FOR_CONFIDENCE:
            warnings.warn(
                f"Peu d'offres actives sur CS.Money pour '{item_name}' ({offer_count} offres, "
                f"seuil de confiance : {MIN_VOLUME_FOR_CONFIDENCE}) — prix potentiellement peu fiable"
            )

        amount = Decimal(str(item["minPrice"]))
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _to_slug(self, item_name: str) -> str:
        return build_slug(item_name)

    def _fetch(self, slug: str) -> str:
        url = f"{BASE_URL}/{self._locale}/csgo/{slug}/"
        for attempt in range(MAX_ATTEMPTS):
            time.sleep(THROTTLE_SECONDS)
            response = requests.get(url, timeout=10)
            if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            if response.status_code == 429:
                raise CSMoneyError(
                    f"CS.Money limite les requêtes (429) pour '{slug}', même après "
                    f"{MAX_ATTEMPTS} tentatives"
                )
            if response.status_code == 404:
                raise CSMoneyError(f"CS.Money n'a pas trouvé de prix pour '{slug}'")
            response.raise_for_status()
            # CS.Money ne déclare pas de charset dans son Content-Type, donc
            # requests retombe sur ISO-8859-1 par défaut (RFC 2616) au lieu
            # d'UTF-8, ce qui corrompt les caractères comme "★" ou "™".
            response.encoding = "utf-8"
            return response.text

    def _parse_item(self, html: str, item_name: str) -> dict:
        match = PAGE_PARAMS_PATTERN.search(html)
        if match is None:
            raise CSMoneyError(f"Impossible de lire les données CS.Money pour '{item_name}'")

        try:
            data = json.loads(match.group(1))
            item = data["data"]["itemDetails"]["item"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise CSMoneyError(
                f"Impossible de lire les données CS.Money pour '{item_name}'"
            ) from error

        # Le slug deviné peut résoudre vers un item différent (mauvaise
        # supposition de format) : on vérifie le nom retourné plutôt que de
        # comparer silencieusement le mauvais prix.
        if item.get("fullName") != item_name:
            raise CSMoneyError(
                f"CS.Money a renvoyé un item différent pour '{item_name}' "
                f"(reçu : '{item.get('fullName')}')"
            )

        if item.get("minPrice") is None:
            raise CSMoneyError(f"Aucune offre de vente active sur CS.Money pour '{item_name}'")

        return item
