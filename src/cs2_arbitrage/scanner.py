from decimal import Decimal
from urllib.parse import urlparse

import requests

from cs2_arbitrage.compare import Opportunity, compare, profit_percent
from cs2_arbitrage.normalize import normalize
from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price
from cs2_arbitrage.sources.csdeals import CSDealsError
from cs2_arbitrage.sources.csdeals import fetch_items as fetch_csdeals_items
from cs2_arbitrage.sources.csmoney import CSMoneyError, CSMoneySource
from cs2_arbitrage.sources.marketcsgo import MarketCSGOError
from cs2_arbitrage.sources.marketcsgo import fetch_items as fetch_marketcsgo_items
from cs2_arbitrage.sources.skinport import fetch_items as fetch_skinport_items
from cs2_arbitrage.sources.steam import SteamMarketError, SteamMarketSource
from cs2_arbitrage.sources.waxpeer import WaxpeerError
from cs2_arbitrage.sources.waxpeer import fetch_items as fetch_waxpeer_items
from cs2_arbitrage.sources.whitemarket import WhiteMarketError
from cs2_arbitrage.sources.whitemarket import fetch_items as fetch_whitemarket_items

# Scan de tout le catalogue (par opposition à la sélection manuelle d'items
# dans le navigateur) : limité à Skinport/Waxpeer/CS.Deals/White.market/
# market.csgo.com, les seules sources qui renvoient tout leur catalogue en
# un appel. Steam et CS.Money n'ont pas cet endpoint : leur prix se
# récupère un item à la fois, avec throttle (1.5s / 0.7s) — scanner
# ~25 000 items dessus prendrait des heures. Décision utilisateur du
# 2026-08-03 : les exclure d'office pour cette fonctionnalité plutôt que
# d'exposer un mode "lent" avec avertissement.
#
# Skinport sert de plateforme de référence pour le seuil de prix (décision
# utilisateur du 2026-08-03) : c'est déjà la source du catalogue de
# navigation ailleurs dans l'app, et la plus complète des 5 (~25 000
# items). Un item qualifie si son prix Skinport est sous le seuil ; ses
# prix Waxpeer/CS.Deals/White.market/market.csgo.com (jambe de vente
# potentielle) sont inclus tels quels, même au-dessus du seuil. Limite
# connue : un item absent de Skinport mais présent (et bon marché) ailleurs
# ne peut jamais qualifier — accepté vu que Skinport est déjà la source la
# plus large.
#
# Filtrage par liquidité (MIN_VOLUME_FOR_CONFIDENCE, même seuil que les
# sources individuelles) : repéré le 2026-08-03 qu'au-delà des cas extrêmes
# déjà exclus par compare.MAX_SANE_PROFIT_PERCENT, une bonne partie des
# opportunités "à la limite" (~100% de profit) reposaient sur des items
# Waxpeer à 1-2 offres seulement (prix pas fiable, cf. sources/waxpeer.py).
# Contrairement au mode manuel (get_price avertit mais n'exclut pas), un
# scan sur tout le catalogue ne peut pas se permettre d'afficher un
# avertissement par item douteux parmi des milliers de résultats : on
# exclut directement plutôt que de compter sur une lecture attentive.
# CS.Deals n'a pas de champ de volume/offres (cf. sources/csdeals.py) :
# pas de filtre possible sur cette source.

# Filtre par catégorie (décision utilisateur du 2026-08-03, suite à des
# opportunités jugées peu fiables sur des stickers à liquidité fine) :
# contrairement au navigateur manuel (catalog.py TYPE_LABELS), limité aux
# skins d'armes, le scan porte sur tout le catalogue Skinport donc expose
# toutes les catégories qui ont un volume significatif d'items (vérifié en
# réel le 2026-08-03 : gift/tag/tool ont 1 à 3 items au total sur ~25 000,
# exclues comme non pertinentes). Skinport étant la plateforme de référence
# du scan, filtrer sur sa catégorie suffit à filtrer tout le scan (cf.
# fetch_scan_prices : seuls les noms qualifiés par Skinport sont retenus,
# quelle que soit leur catégorie sur les autres sources).
SCAN_CATEGORY_LABELS = {
    "rifle": "Fusils",
    "pistol": "Pistolets",
    "smg": "SMG",
    "heavy": "Heavy",
    "knife": "Couteaux",
    "gloves": "Gants",
    "sticker": "Stickers",
    "graffiti": "Graffitis",
    "container": "Caisses",
    "charm": "Porte-clés",
    "music-kit": "Kits musicaux",
    "patch": "Patchs",
    "agent": "Agents",
    "equipment": "Équipement",
    "collectible": "Objets de collection",
    "pass": "Pass",
    "key": "Clés",
}


def _scan_category_slug(market_page: str) -> str | None:
    parts = [p for p in urlparse(market_page).path.split("/") if p]
    # ex: ["market", "rifle", "ak-47"] -> "rifle"
    return parts[1] if len(parts) > 1 else None


def _skinport_catalog_prices(categories: set[str] | None = None):
    for item in fetch_skinport_items(currency="USD"):
        if item.get("min_price") is None:
            continue
        if categories is not None and _scan_category_slug(item["market_page"]) not in categories:
            continue
        quantity = item.get("quantity")
        if quantity is not None and int(quantity) < MIN_VOLUME_FOR_CONFIDENCE:
            continue
        yield item["market_hash_name"], Decimal(str(item["min_price"])), "skinport"


def _waxpeer_catalog_prices():
    for item in fetch_waxpeer_items():
        count = item.get("count")
        if count is not None and int(count) < MIN_VOLUME_FOR_CONFIDENCE:
            continue
        yield item["name"], Decimal(item["min"]) / 1000, "waxpeer"


def _csdeals_catalog_prices():
    for item in fetch_csdeals_items():
        yield item["marketname"], Decimal(item["lowest_price"]), "csdeals"


def _whitemarket_catalog_prices():
    for item in fetch_whitemarket_items():
        count = item.get("market_product_count")
        if count is not None and int(count) < MIN_VOLUME_FOR_CONFIDENCE:
            continue
        yield item["market_hash_name"], Decimal(item["price"]), "whitemarket"


def _marketcsgo_catalog_prices():
    for item in fetch_marketcsgo_items():
        volume = item.get("volume")
        if volume is not None and int(volume) < MIN_VOLUME_FOR_CONFIDENCE:
            continue
        yield item["market_hash_name"], Decimal(item["price"]), "marketcsgo"


def _safe_catalog_prices(source_label: str, catalog_prices_fn, *expected_errors):
    """Isole une jambe de vente optionnelle du scan (Waxpeer/CS.Deals/
    White.market/market.csgo.com) : si sa récupération échoue, on avertit et
    on continue avec les autres plutôt que de perdre tout le scan pour une
    seule source en panne. Repéré le 2026-08-11 : CS.Deals bloque désormais
    ses appels sans navigateur derrière une protection Cloudflare (403
    "challenge" sur le site entier, pas juste l'API) suite à sa migration
    v2.0 — sans ce garde-fou, un `requests.exceptions.HTTPError` non
    intercepté y faisait planter fetch_scan_prices en entier, y compris les
    3 autres sources pourtant fonctionnelles. Skinport (référence du scan)
    n'est volontairement pas concerné : sans lui, il n'y a de toute façon
    aucun item à scanner."""
    try:
        return list(catalog_prices_fn())
    except (requests.RequestException, *expected_errors) as error:
        print(f"[avertissement] {source_label} indisponible pour le scan : {error}")
        return []


def fetch_scan_prices(
    min_price: Decimal, max_price: Decimal, categories: set[str] | None = None
) -> list[Price]:
    """Prix, sur Skinport/Waxpeer/CS.Deals/White.market, de tout item dont
    le prix Skinport (plateforme de référence) est entre min_price et
    max_price (bornes incluses). Un seul appel réseau par plateforme (4 au
    total), quel que soit le nombre d'items retenus : le filtrage par prix
    se fait ensuite en mémoire, pas côté API.

    min_price sert surtout à écarter le bruit des items à 1-2 centimes,
    où un écart de prix "à 100%" ne représente souvent que le pas minimum
    de cotation entre deux plateformes plutôt qu'une vraie opportunité
    (cf. compare.MAX_SANE_PROFIT_PERCENT pour le filtre symétrique côté
    profit relatif).

    categories restreint aux slugs Skinport indiqués (cf.
    SCAN_CATEGORY_LABELS) ; None (par défaut) ne filtre pas.

    Les prix Waxpeer/CS.Deals/White.market/market.csgo.com des items
    qualifiés sont inclus tels quels, même au-dessus de max_price (jambe de
    vente potentielle — c'est tout l'intérêt de l'arbitrage)."""
    skinport_prices = list(_skinport_catalog_prices(categories))
    qualifying_items = {
        name for name, amount, _ in skinport_prices if min_price <= amount <= max_price
    }

    prices = []
    for name, amount, source in (
        *skinport_prices,
        *_safe_catalog_prices("Waxpeer", _waxpeer_catalog_prices, WaxpeerError),
        *_safe_catalog_prices("CS.Deals", _csdeals_catalog_prices, CSDealsError),
        *_safe_catalog_prices("White.market", _whitemarket_catalog_prices, WhiteMarketError),
        *_safe_catalog_prices("market.csgo.com", _marketcsgo_catalog_prices, MarketCSGOError),
    ):
        if name in qualifying_items:
            prices.append(Price(item_name=name, amount=amount, currency="USD", source=source))
    return prices


def _opportunities_from_prices(prices: list[Price]) -> list[Opportunity]:
    normalized_prices = [normalize(price) for price in prices]
    opportunities = compare(normalized_prices)
    return [opportunity for opportunity in opportunities if opportunity.profit > 0]


def run_catalog_scan(
    min_price: Decimal, max_price: Decimal, categories: set[str] | None = None
) -> list[Opportunity]:
    """Opportunités rentables sur tout le catalogue entre min_price et
    max_price, restreint aux catégories indiquées (cf. fetch_scan_prices).
    Ne renvoie que les opportunités profitables (profit > 0) : contrairement
    à la sélection manuelle d'items, où l'utilisateur veut voir même les
    items sans opportunité qu'il a choisis exprès, un scan large n'a
    d'intérêt que pour les vraies trouvailles."""
    prices = fetch_scan_prices(min_price, max_price, categories)
    return _opportunities_from_prices(prices)


# Steam et CS.Money sont throttlés (1.5s / 0.7s entre requêtes) donc exclus
# du scan complet (cf. plus haut, "des heures sur ~25 000 items"), mais un
# scan les ignore alors totalement, même pour ses meilleurs candidats —
# alors qu'interroger une trentaine d'items un par un, au lieu de tout le
# catalogue, reste rapide (~1 minute) et sans risque de rate-limit. Ajouté
# le 2026-08-04 suite à une question utilisateur en ce sens. Volontairement
# plus large que TOP_TRADES_COUNT (10, gui.py) : un item peut grimper dans
# le top 10 final GRÂCE à un meilleur prix Steam/CS.Money (ex: un meilleur
# prix de vente sur Steam qui ferait grimper un item classé 15e sans lui),
# donc le classement doit être recalculé une fois ces deux sources
# ajoutées, pas seulement recalculé sur les 10 déjà en tête sans elles.
ENRICH_CANDIDATE_COUNT = 30

THROTTLED_ENRICHMENT_SOURCES = [
    SteamMarketSource(currency="USD"),
    CSMoneySource(currency="USD"),
]


def _top_candidate_item_names(opportunities: list[Opportunity], count: int) -> list[str]:
    best_profit_percent: dict[str, Decimal] = {}
    for opportunity in opportunities:
        percent = profit_percent(opportunity)
        current = best_profit_percent.get(opportunity.item_name)
        if current is None or percent > current:
            best_profit_percent[opportunity.item_name] = percent
    ranked = sorted(best_profit_percent, key=best_profit_percent.get, reverse=True)
    return ranked[:count]


def enrich_top_opportunities(
    prices: list[Price],
    opportunities: list[Opportunity],
    candidate_count: int = ENRICH_CANDIDATE_COUNT,
) -> list[Opportunity]:
    """Recalcule les opportunités des `candidate_count` meilleurs items du
    scan (par profit relatif, cf. _top_candidate_item_names) en y ajoutant
    Steam et CS.Money, les deux seules sources absentes du scan complet.
    Les opportunités des items hors de ce top ne sont pas modifiées."""
    candidate_names = set(_top_candidate_item_names(opportunities, candidate_count))
    if not candidate_names:
        return opportunities

    print(
        f"Enrichissement des {len(candidate_names)} meilleurs candidats avec Steam et "
        f"CS.Money (throttlé, ~1 minute)..."
    )
    candidate_prices = [price for price in prices if price.item_name in candidate_names]
    for source in THROTTLED_ENRICHMENT_SOURCES:
        for item_name in candidate_names:
            try:
                candidate_prices.append(source.get_price(item_name))
            except (SteamMarketError, CSMoneyError) as error:
                print(f"[avertissement] {error}")

    enriched_candidate_opportunities = _opportunities_from_prices(candidate_prices)
    unaffected_opportunities = [
        opportunity for opportunity in opportunities if opportunity.item_name not in candidate_names
    ]
    return unaffected_opportunities + enriched_candidate_opportunities


def scan_and_enrich_catalog(
    min_price: Decimal,
    max_price: Decimal,
    categories: set[str] | None = None,
    candidate_count: int = ENRICH_CANDIDATE_COUNT,
) -> list[Opportunity]:
    """Point d'entrée utilisé par main.py pour le flux "scan catalogue" :
    scan complet (run_catalog_scan) puis enrichissement Steam/CS.Money des
    meilleurs candidats (cf. enrich_top_opportunities)."""
    prices = fetch_scan_prices(min_price, max_price, categories)
    opportunities = _opportunities_from_prices(prices)
    return enrich_top_opportunities(prices, opportunities, candidate_count)
