import sys

from cs2_arbitrage.compare import compare
from cs2_arbitrage.normalize import normalize
from cs2_arbitrage.report import generate_report
from cs2_arbitrage.sources.skinport import SkinportError, SkinportSource
from cs2_arbitrage.sources.steam import SteamMarketError, SteamMarketSource

# La console Windows encode stdout en cp1252 par défaut, qui ne sait pas
# afficher certains caractères présents dans les noms d'items (ex: ★).
sys.stdout.reconfigure(encoding="utf-8")

# Liste de test volontairement variée : rifles/pistolets/couteaux, StatTrak
# et non-StatTrak, du très bon marché au très cher. Les couteaux ont un
# préfixe "★ " dans leur market_hash_name officiel (vérifié contre le vrai
# catalogue Skinport).
ITEMS = [
    "AK-47 | Nouveau Rouge (Minimal Wear)",
    "★ Nomad Knife | Tiger Tooth (Factory New)",
    "AK-47 | Redline (Field-Tested)",
    "AWP | Asiimov (Field-Tested)",
    "StatTrak™ AK-47 | Redline (Field-Tested)",
    "Glock-18 | Fade (Factory New)",
    "Desert Eagle | Blaze (Factory New)",
    "USP-S | Kill Confirmed (Minimal Wear)",
    "★ Karambit | Doppler (Factory New)",
    "P250 | Sand Dune (Battle-Scarred)",
]

SOURCES = [SteamMarketSource(currency="EUR"), SkinportSource(currency="EUR")]


def collect_normalized_prices(items, sources):
    normalized_prices = []
    for item_name in items:
        for source in sources:
            try:
                price = source.get_price(item_name)
            except (SteamMarketError, SkinportError) as error:
                print(f"[avertissement] {error}")
                continue
            normalized_prices.append(normalize(price))
    return normalized_prices


def main():
    normalized_prices = collect_normalized_prices(ITEMS, SOURCES)
    opportunities = compare(normalized_prices)
    print(generate_report(opportunities))


if __name__ == "__main__":
    main()
