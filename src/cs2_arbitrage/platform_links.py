from functools import lru_cache
from urllib.parse import quote

import requests

from cs2_arbitrage.sources.csmoney import BASE_URL as CSMONEY_BASE_URL
from cs2_arbitrage.sources.csmoney import build_slug as build_csmoney_slug
from cs2_arbitrage.sources.skinport import SkinportError
from cs2_arbitrage.sources.skinport import fetch_items as fetch_skinport_items
from cs2_arbitrage.sources.steam import CS2_APP_ID
from cs2_arbitrage.sources.whitemarket import WhiteMarketError
from cs2_arbitrage.sources.whitemarket import fetch_items as fetch_whitemarket_items

# Construit, pour un item et une plateforme donnés, un lien vers sa page
# sur cette plateforme — pour accélérer l'EXÉCUTION MANUELLE d'un trade
# repéré dans le rapport (ReportApp, gui.py), jamais pour placer un ordre
# depuis le code (décision utilisateur du 2026-08-04 : pas d'automatisation
# de trading, l'utilisateur clique/valide chaque trade lui-même).
#
# Chaque lien est vérifié par comparaison de contenu réel/faux item (pas
# juste un statut HTTP 200, insuffisant sur une SPA — cf. incident du
# 2026-08-04 ci-dessous) :
# - Lien direct, item réel confirmé : Skinport (`item_page`, champ dédié
#   dans son dump), White.market (`market_product_link`, idem), Steam et
#   CS.Money (URL reconstruite depuis market_hash_name — og:title/404
#   diffèrent bien entre un item réel et un slug bidon, vérifié).
# - Lien vers la page marché générale, PAS de recherche vérifiable :
#   CS.Deals et market.csgo.com sont des SPA intégralement rendues côté
#   client (Vue/Angular) — aucun paramètre de requête testé (name, search,
#   q, query, term, en chemin ou en query string) ne produit de différence
#   de contenu HTML mesurable entre deux requêtes, preuve qu'aucun état
#   n'est lu côté serveur au chargement. Waxpeer expose un vrai paramètre
#   `?search=` (le champ de recherche est pré-rempli côté serveur, vérifié)
#   mais pas de page item individuelle adressable depuis son dump — sa
#   vraie route "/{slug}/item/{id}" a besoin d'un ID numérique absent du
#   catalogue bulk. Incident du 2026-08-04 : une v1 de ce module
#   construisait "/item/{slug}" pour Waxpeer (slug dérivé de l'URL de son
#   image CDN) en le faisant passer pour un lien direct — retour
#   utilisateur ("ça renvoie sur la page d'accueil") + vérification
#   og:title/h1 identiques entre item réel et slug bidon ont confirmé que
#   ce n'était pas une vraie route, juste une réponse générique.
STEAM_LISTING_URL = "https://steamcommunity.com/market/listings/{app_id}/{item}"
WAXPEER_SEARCH_URL = "https://waxpeer.com/en/market?search={item}"
CSDEALS_MARKET_URL = "https://cs.deals/market/730"
MARKETCSGO_MARKET_URL = "https://market.csgo.com/en/"


@lru_cache(maxsize=1)
def _skinport_item_pages() -> dict[str, str]:
    try:
        items = fetch_skinport_items(currency="USD")
    except (requests.RequestException, SkinportError):
        return {}
    return {item["market_hash_name"]: item["item_page"] for item in items if item.get("item_page")}


@lru_cache(maxsize=1)
def _whitemarket_links() -> dict[str, str]:
    try:
        items = fetch_whitemarket_items()
    except (requests.RequestException, WhiteMarketError):
        return {}
    return {
        item["market_hash_name"]: item["market_product_link"]
        for item in items
        if item.get("market_product_link")
    }


def build_item_url(source: str, item_name: str) -> str | None:
    """Lien vers `item_name` sur `source`, ou None si indisponible (item
    absent du catalogue, réseau indisponible...) — à l'appelant (gui.py)
    de ne simplement pas afficher de lien dans ce cas, pas de traiter ça
    comme une erreur."""
    if source == "skinport":
        return _skinport_item_pages().get(item_name)
    if source == "whitemarket":
        return _whitemarket_links().get(item_name)
    if source == "waxpeer":
        return WAXPEER_SEARCH_URL.format(item=quote(item_name))
    if source == "steam":
        return STEAM_LISTING_URL.format(app_id=CS2_APP_ID, item=quote(item_name))
    if source == "csmoney":
        return f"{CSMONEY_BASE_URL}/en/csgo/{build_csmoney_slug(item_name)}/"
    if source == "csdeals":
        return CSDEALS_MARKET_URL
    if source == "marketcsgo":
        return MARKETCSGO_MARKET_URL
    return None
