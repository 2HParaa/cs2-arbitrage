from collections import defaultdict

from cs2_arbitrage.compare import Opportunity

STEAM_WALLET_WARNING = "Steam Wallet uniquement, non retirable en cash"


def generate_report(opportunities: list[Opportunity]) -> str:
    by_item = defaultdict(list)
    for opportunity in opportunities:
        by_item[opportunity.item_name].append(opportunity)

    lines = ["=== Rapport d'arbitrage CS2 ==="]
    for item_name, item_opportunities in by_item.items():
        profitable = sorted(
            (o for o in item_opportunities if o.profit > 0),
            key=lambda o: o.profit,
            reverse=True,
        )
        lines.append("")
        lines.append(item_name)
        if not profitable:
            lines.append("  Aucune opportunité rentable.")
            continue
        for opportunity in profitable:
            lines.append(f"  {_format_opportunity(opportunity)}")

    return "\n".join(lines)


def _format_opportunity(opportunity: Opportunity) -> str:
    line = (
        f"Acheter sur {opportunity.buy_source} ({opportunity.buy_price} {opportunity.currency}) "
        f"-> Vendre sur {opportunity.sell_source} "
        f"(net {opportunity.sell_net_price} {opportunity.currency}) "
        f"| Profit : +{opportunity.profit} {opportunity.currency}"
    )
    if not opportunity.cash_realizable:
        line += f" [{STEAM_WALLET_WARNING}]"
    return line
