from decimal import Decimal

from cs2_arbitrage.compare import Opportunity, compare
from cs2_arbitrage.normalize import normalize
from cs2_arbitrage.sources.base import MIN_VOLUME_FOR_CONFIDENCE, Price
from cs2_arbitrage.sources.csdeals import fetch_items as fetch_csdeals_items
from cs2_arbitrage.sources.skinport import fetch_items as fetch_skinport_items
from cs2_arbitrage.sources.waxpeer import fetch_items as fetch_waxpeer_items
from cs2_arbitrage.sources.whitemarket import fetch_items as fetch_whitemarket_items

# Scan de tout le catalogue (par opposition à la sélection manuelle d'items
# dans le navigateur) : limité à Skinport/Waxpeer/CS.Deals/White.market,
# les seules sources qui renvoient tout leur catalogue en un appel. Steam
# et CS.Money n'ont pas cet endpoint : leur prix se récupère un item à la
# fois, avec throttle (1.5s / 0.7s) — scanner ~25 000 items dessus
# prendrait des heures. Décision utilisateur du 2026-08-03 : les exclure
# d'office pour cette fonctionnalité plutôt que d'exposer un mode "lent"
# avec avertissement.
#
# Skinport sert de plateforme de référence pour le seuil de prix (décision
# utilisateur du 2026-08-03) : c'est déjà la source du catalogue de
# navigation ailleurs dans l'app, et la plus complète des 4 (~25 000
# items). Un item qualifie si son prix Skinport est sous le seuil ; ses
# prix Waxpeer/CS.Deals/White.market (jambe de vente potentielle) sont
# inclus tels quels, même au-dessus du seuil. Limite connue : un item
# absent de Skinport mais présent (et bon marché) ailleurs ne peut jamais
# qualifier — accepté vu que Skinport est déjà la source la plus large.
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


def _skinport_catalog_prices():
    for item in fetch_skinport_items(currency="USD"):
        if item.get("min_price") is None:
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


def fetch_scan_prices(min_price: Decimal, max_price: Decimal) -> list[Price]:
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

    Les prix Waxpeer/CS.Deals/White.market des items qualifiés sont inclus
    tels quels, même au-dessus de max_price (jambe de vente potentielle —
    c'est tout l'intérêt de l'arbitrage)."""
    skinport_prices = list(_skinport_catalog_prices())
    qualifying_items = {
        name for name, amount, _ in skinport_prices if min_price <= amount <= max_price
    }

    prices = []
    for name, amount, source in (
        *skinport_prices,
        *_waxpeer_catalog_prices(),
        *_csdeals_catalog_prices(),
        *_whitemarket_catalog_prices(),
    ):
        if name in qualifying_items:
            prices.append(Price(item_name=name, amount=amount, currency="USD", source=source))
    return prices


def run_catalog_scan(min_price: Decimal, max_price: Decimal) -> list[Opportunity]:
    """Opportunités rentables sur tout le catalogue entre min_price et
    max_price. Ne renvoie que les opportunités profitables (profit > 0) :
    contrairement à la sélection manuelle d'items, où l'utilisateur veut
    voir même les items sans opportunité qu'il a choisis exprès, un scan
    large n'a d'intérêt que pour les vraies trouvailles."""
    prices = fetch_scan_prices(min_price, max_price)
    normalized_prices = [normalize(price) for price in prices]
    opportunities = compare(normalized_prices)
    return [opportunity for opportunity in opportunities if opportunity.profit > 0]
