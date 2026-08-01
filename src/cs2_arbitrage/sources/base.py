from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


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
