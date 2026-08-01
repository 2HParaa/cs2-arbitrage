from decimal import Decimal

import pytest

from cs2_arbitrage.normalize import NormalizedPrice, normalize
from cs2_arbitrage.sources.base import Price


def test_normalize_deduces_steam_fee_with_additive_model():
    # Steam calcule 15% sur le montant recu, puis l'ajoute au prix affiche :
    # affiche = recu * 1.15 => recu = affiche / 1.15
    price = Price(
        item_name="AK-47 | Redline", amount=Decimal("100.00"), currency="EUR", source="steam"
    )

    result = normalize(price)

    assert result == NormalizedPrice(
        item_name="AK-47 | Redline",
        currency="EUR",
        source="steam",
        gross_amount=Decimal("100.00"),
        net_amount=Decimal("86.96"),
    )


def test_normalize_deduces_skinport_fee_with_subtractive_model():
    # Skinport deduit 8% directement du prix affiche : recu = affiche * 0.92
    price = Price(
        item_name="AK-47 | Redline", amount=Decimal("100.00"), currency="EUR", source="skinport"
    )

    result = normalize(price)

    assert result.net_amount == Decimal("92.00")


def test_normalize_rounds_steam_net_amount_to_the_cent():
    price = Price(
        item_name="AK-47 | Redline", amount=Decimal("10.00"), currency="EUR", source="steam"
    )

    result = normalize(price)

    assert result.net_amount == Decimal("8.70")


def test_normalize_rounds_skinport_net_amount_to_the_cent():
    price = Price(
        item_name="AK-47 | Redline", amount=Decimal("12.345"), currency="EUR", source="skinport"
    )

    result = normalize(price)

    assert result.net_amount == Decimal("11.36")


def test_normalize_raises_for_unknown_source():
    price = Price(
        item_name="AK-47 | Redline", amount=Decimal("10.00"), currency="EUR", source="cs.money"
    )

    with pytest.raises(KeyError):
        normalize(price)
