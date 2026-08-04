from functools import lru_cache
from urllib.parse import quote

import requests

from cs2_arbitrage.sources.csmoney import BASE_URL as CSMONEY_BASE_URL
from cs2_arbitrage.sources.csmoney import build_slug as build_csmoney_slug
from cs2_arbitrage.sources.skinport import SkinportError
from cs2_arbitrage.sources.skinport import fetch_items as fetch_skinport_items
from cs2_arbitrage.sources.steam import CS2_APP_ID
from cs2_arbitrage.sources.waxpeer import WaxpeerError
from cs2_arbitrage.sources.waxpeer import fetch_items as fetch_waxpeer_items
from cs2_arbitrage.sources.whitemarket import WhiteMarketError
from cs2_arbitrage.sources.whitemarket import fetch_items as fetch_whitemarket_items

# Construit, pour un item et une plateforme donnés, un lien vers sa page
# sur cette plateforme — pour accélérer l'EXÉCUTION MANUELLE d'un trade
# repéré dans le rapport (ReportApp, gui.py), jamais pour placer un ordre
# depuis le code (décision utilisateur du 2026-08-04 : pas d'automatisation
# de trading, l'utilisateur clique/valide chaque trade lui-même).
#
# Deux catégories de lien, selon ce que chaque plateforme expose :
# - Lien direct vers l'item (Skinport, White.market : champ dédié dans
#   leur dump ; Steam, CS.Money : URL reconstruite depuis market_hash_name,
#   schéma d'URL stable et bien connu ; Waxpeer : slug dérivé de l'URL de
#   son image CDN, seul endroit où ce schéma apparaît dans son dump).
# - Lien "meilleur effort" vers la recherche (CS.Deals, market.csgo.com) :
#   ni l'un ni l'autre n'expose de champ d'URL ni de slug dans son dump, et
#   ce sont des SPA (rendu côté client) — impossible de vérifier par un
#   simple appel HTTP que la recherche filtre bien sur l'item exact. Pas
#   une garantie de tomber pile dessus, mais jamais un cul-de-sac non plus.
STEAM_LISTING_URL = "https://steamcommunity.com/market/listings/{app_id}/{item}"
CSDEALS_SEARCH_URL = "https://cs.deals/market/730?name={item}"
MARKETCSGO_SEARCH_URL = "https://market.csgo.com/en/?search={item}"
# Vérifié en réel le 2026-08-04 : les images CDN Waxpeer suivent le schéma
# ".../i/730-{slug}.webp", et "https://waxpeer.com/item/{slug}" charge bien
# avec ce même slug (minuscules, tirets — même schéma que Skinport/
# White.market). Waxpeer n'expose ce slug nulle part ailleurs dans son
# dump : c'est le seul moyen de le récupérer sans le recalculer soi-même.
WAXPEER_ITEM_URL = "https://waxpeer.com/item/{slug}"


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


@lru_cache(maxsize=1)
def _waxpeer_slugs() -> dict[str, str]:
    try:
        items = fetch_waxpeer_items()
    except (requests.RequestException, WaxpeerError):
        return {}
    slugs = {}
    for item in items:
        image_url = item.get("img")
        if not image_url:
            continue
        filename = image_url.rsplit("/", 1)[-1].removesuffix(".webp")
        slug = filename.removeprefix(f"{CS2_APP_ID}-")
        slugs[item["name"]] = slug
    return slugs


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
        slug = _waxpeer_slugs().get(item_name)
        return WAXPEER_ITEM_URL.format(slug=slug) if slug else None
    if source == "steam":
        return STEAM_LISTING_URL.format(app_id=CS2_APP_ID, item=quote(item_name))
    if source == "csmoney":
        return f"{CSMONEY_BASE_URL}/en/csgo/{build_csmoney_slug(item_name)}/"
    if source == "csdeals":
        return CSDEALS_SEARCH_URL.format(item=quote(item_name))
    if source == "marketcsgo":
        return MARKETCSGO_SEARCH_URL.format(item=quote(item_name))
    return None
