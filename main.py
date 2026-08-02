import sys

from cs2_arbitrage.compare import compare
from cs2_arbitrage.gui import run_item_browser
from cs2_arbitrage.normalize import normalize
from cs2_arbitrage.report import generate_report
from cs2_arbitrage.sources.csmoney import CSMoneyError, CSMoneySource
from cs2_arbitrage.sources.skinport import SkinportError, SkinportSource
from cs2_arbitrage.sources.steam import SteamMarketError, SteamMarketSource

# La console Windows encode stdout/stderr en cp1252 par défaut, qui ne sait
# pas afficher certains caractères présents dans les noms d'items (ex: ★) ni
# dans les warnings (ex: —). stderr est le flux utilisé par warnings.warn()
# et, plus tard, par le module logging si on l'ajoute.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SOURCES = [
    SteamMarketSource(currency="EUR"),
    SkinportSource(currency="EUR"),
    CSMoneySource(currency="EUR"),
]


def collect_normalized_prices(items, sources):
    normalized_prices = []
    for item_name in items:
        for source in sources:
            try:
                price = source.get_price(item_name)
            except (SteamMarketError, SkinportError, CSMoneyError) as error:
                print(f"[avertissement] {error}")
                continue
            normalized_prices.append(normalize(price))
    return normalized_prices


def main():
    items, selected_platforms = run_item_browser()
    if not items or not selected_platforms:
        print("Aucun item ou aucune plateforme sélectionnée.")
        return

    sources = [source for source in SOURCES if source.name in selected_platforms]
    normalized_prices = collect_normalized_prices(items, sources)
    opportunities = compare(normalized_prices)
    print(generate_report(opportunities))


if __name__ == "__main__":
    main()
