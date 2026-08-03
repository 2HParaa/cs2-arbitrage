from decimal import Decimal
from functools import lru_cache

import requests

RATE_URL = "https://api.frankfurter.app/latest"

# API publique, aucune clé requise (vérifié en réel le 2026-08-03) : taux
# de change officiels de la Banque centrale européenne, mis à jour un jour
# ouvré sur deux (rythme de publication de la BCE elle-même). Utilisé
# uniquement pour l'AFFICHAGE dans la GUI (l'utilisateur est français) :
# le pipeline (sources, normalize.py, compare.py) reste entièrement en USD
# — cf. main.py, Waxpeer/CS.Deals ne renvoyant leurs prix qu'en USD.


class ExchangeRateError(Exception):
    """Erreur lors de la récupération du taux de change USD -> EUR."""


@lru_cache(maxsize=1)
def fetch_usd_to_eur_rate() -> Decimal:
    """Taux de change USD -> EUR du jour. Mis en cache pour la durée du
    process : un seul appel réseau par session, pas un par montant affiché."""
    try:
        response = requests.get(RATE_URL, params={"from": "USD", "to": "EUR"}, timeout=10)
        response.raise_for_status()
        data = response.json()
        return Decimal(str(data["rates"]["EUR"]))
    except (requests.RequestException, KeyError, ValueError) as error:
        raise ExchangeRateError("Impossible de récupérer le taux de change USD -> EUR") from error
