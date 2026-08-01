import time
from decimal import Decimal

import requests

from cs2_arbitrage.sources.base import Price, PriceSource

CS2_APP_ID = 730
PRICE_OVERVIEW_URL = "https://steamcommunity.com/market/priceoverview/"
CURRENCY_IDS = {"USD": 1, "EUR": 3}

# Steam limite le nombre de requêtes sur cet endpoint (non documenté
# officiellement, cf. CLAUDE.md). On espace chaque appel pour éviter de
# déclencher la limite, et on réessaie avec un délai croissant si ça arrive
# quand même, plutôt que de faire planter tout le script.
THROTTLE_SECONDS = 3
MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 10


class SteamMarketError(Exception):
    """Erreur lors de la récupération d'un prix sur Steam Community Market."""


class SteamMarketSource(PriceSource):
    def __init__(self, currency: str = "EUR"):
        self._currency = currency
        self._currency_id = CURRENCY_IDS[currency]

    @property
    def name(self) -> str:
        return "steam"

    def get_price(self, item_name: str) -> Price:
        data = self._fetch(item_name)

        if not data.get("success"):
            raise SteamMarketError(f"Steam n'a pas trouvé de prix pour '{item_name}'")

        amount = self._parse_amount(data["lowest_price"])
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _fetch(self, item_name: str) -> dict:
        for attempt in range(MAX_ATTEMPTS):
            time.sleep(THROTTLE_SECONDS)
            response = requests.get(
                PRICE_OVERVIEW_URL,
                params={
                    "appid": CS2_APP_ID,
                    "currency": self._currency_id,
                    "market_hash_name": item_name,
                },
                timeout=10,
            )
            if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            if response.status_code == 429:
                raise SteamMarketError(
                    f"Steam limite les requêtes (429) pour '{item_name}', même après {MAX_ATTEMPTS} tentatives"
                )
            response.raise_for_status()
            return response.json()

    def _parse_amount(self, raw_price: str) -> Decimal:
        # Le séparateur de milliers (espace en EUR : "1 234,56 €") est filtré
        # ici car il n'est ni un chiffre ni "," / ".".
        digits = "".join(char for char in raw_price if char.isdigit() or char in ",.")
        if self._currency == "USD":
            # format "1,234.56" : virgule = milliers, point = décimales
            digits = digits.replace(",", "")
        else:
            # format EUR "1234,56" : virgule = décimales
            digits = digits.replace(",", ".")
        return Decimal(digits)
