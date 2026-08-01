from decimal import Decimal

import pytest

from cs2_arbitrage.sources.base import Price, PriceSource


class DummySource(PriceSource):
    @property
    def name(self) -> str:
        return "dummy"

    def get_price(self, item_name: str) -> Price:
        return Price(item_name=item_name, amount=Decimal("10.50"), currency="EUR", source=self.name)


def test_price_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        PriceSource()


def test_concrete_subclass_returns_price():
    source = DummySource()

    price = source.get_price("AK-47 | Redline")

    assert price == Price(
        item_name="AK-47 | Redline",
        amount=Decimal("10.50"),
        currency="EUR",
        source="dummy",
    )
