from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

# Seuil minimum de liquidité (nombre de ventes/offres actives récentes) en
# dessous duquel un prix est considéré peu fiable statistiquement. Pas de
# valeur "scientifiquement correcte" ici : compromis fiabilité/couverture
# choisi par l'utilisateur, partagé par toutes les plateformes pour rester
# cohérent d'une source à l'autre.
MIN_VOLUME_FOR_CONFIDENCE = 10


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
