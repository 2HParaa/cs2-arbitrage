import sys

from cs2_arbitrage.compare import compare
from cs2_arbitrage.gui import run_item_browser, show_report
from cs2_arbitrage.normalize import normalize
from cs2_arbitrage.report import generate_report
from cs2_arbitrage.scanner import run_catalog_scan
from cs2_arbitrage.sources.csdeals import CSDealsError, CSDealsSource
from cs2_arbitrage.sources.csmoney import CSMoneyError, CSMoneySource
from cs2_arbitrage.sources.skinport import SkinportError, SkinportSource
from cs2_arbitrage.sources.steam import SteamMarketError, SteamMarketSource
from cs2_arbitrage.sources.waxpeer import WaxpeerError, WaxpeerSource

# La console Windows encode stdout/stderr en cp1252 par défaut, qui ne sait
# pas afficher certains caractères présents dans les noms d'items (ex: ★) ni
# dans les warnings (ex: —). stderr est le flux utilisé par warnings.warn()
# et, plus tard, par le module logging si on l'ajoute.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# USD plutôt qu'EUR : Waxpeer (et bientôt d'autres sources) ne renvoie ses
# prix qu'en USD (paramètre currency sans effet, vérifié en réel), et
# compare.py refuse de comparer deux prix en devises différentes. La
# conversion multi-devises est une feature à part, pas encore construite.
SOURCES = [
    SteamMarketSource(currency="USD"),
    SkinportSource(currency="USD"),
    CSMoneySource(currency="USD"),
    WaxpeerSource(),
    CSDealsSource(),
]


def collect_normalized_prices(items, sources):
    normalized_prices = []
    for item_name in items:
        for source in sources:
            try:
                price = source.get_price(item_name)
            except (
                SteamMarketError,
                SkinportError,
                CSMoneyError,
                WaxpeerError,
                CSDealsError,
            ) as error:
                print(f"[avertissement] {error}")
                continue
            normalized_prices.append(normalize(price))
    return normalized_prices


def main():
    items, selected_platforms, scan_max_price = run_item_browser()

    if scan_max_price is not None:
        print(f"Scan du catalogue Skinport/Waxpeer/CS.Deals sous {scan_max_price} USD...")
        opportunities = run_catalog_scan(scan_max_price)
        print(generate_report(opportunities))  # trace texte en console, en plus de la fenêtre
        show_report(opportunities)
        return

    if not items or not selected_platforms:
        print("Aucun item ou aucune plateforme sélectionnée.")
        return

    sources = [source for source in SOURCES if source.name in selected_platforms]
    normalized_prices = collect_normalized_prices(items, sources)
    opportunities = compare(normalized_prices)
    print(generate_report(opportunities))  # trace texte en console, en plus de la fenêtre
    show_report(opportunities)


if __name__ == "__main__":
    main()
