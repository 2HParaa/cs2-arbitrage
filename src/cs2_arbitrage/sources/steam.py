from decimal import Decimal

import requests

from cs2_arbitrage.sources.base import Price, PriceSource

CS2_APP_ID = 730
PRICE_OVERVIEW_URL = "https://steamcommunity.com/market/priceoverview/"
CURRENCY_IDS = {"USD": 1, "EUR": 3}


class SteamMarketError(Exception):
    """Erreur lors de la recuperation d'un prix sur Steam Community Market."""


class SteamMarketSource(PriceSource):
    def __init__(self, currency: str = "EUR"):
        self._currency = currency
        self._currency_id = CURRENCY_IDS[currency]

    @property
    def name(self) -> str:
        return "steam"

    def get_price(self, item_name: str) -> Price:
        response = requests.get(
            PRICE_OVERVIEW_URL,
            params={
                "appid": CS2_APP_ID,
                "currency": self._currency_id,
                "market_hash_name": item_name,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            raise SteamMarketError(f"Steam n'a pas trouve de prix pour '{item_name}'")

        amount = self._parse_amount(data["lowest_price"])
        return Price(item_name=item_name, amount=amount, currency=self._currency, source=self.name)

    def _parse_amount(self, raw_price: str) -> Decimal:
        # Le separateur de milliers (espace en EUR : "1 234,56 €") est filtre
        # ici car il n'est ni un chiffre ni "," / ".".
        digits = "".join(char for char in raw_price if char.isdigit() or char in ",.")
        if self._currency == "USD":
            # format "1,234.56" : virgule = milliers, point = decimales
            digits = digits.replace(",", "")
        else:
            # format EUR "1234,56" : virgule = decimales
            digits = digits.replace(",", ".")
        return Decimal(digits)
