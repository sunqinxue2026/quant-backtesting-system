from datetime import date
from decimal import Decimal

import pytest

from quant_system.engine.models import Side
from quant_system.engine.portfolio import CostModel, Portfolio


def test_buy_cash_fee_slippage_and_t1_sellable():
    portfolio = Portfolio(Decimal("10000"), CostModel(commission_rate=Decimal("0.001"), minimum_commission=Decimal("5"), stamp_tax_rate=Decimal("0.001"), slippage_bps=Decimal("100"), lot_size=100))
    buy = portfolio.settle_trade("000001.SZ", Side.BUY, 100, Decimal("10"), date(2024, 1, 2), 1, 1)
    assert buy.price == Decimal("10.100000")
    assert buy.commission == Decimal("5")
    assert portfolio.cash == Decimal("8985.00")
    assert portfolio.position("000001.SZ").quantity == 100
    assert portfolio.position("000001.SZ").sellable_quantity == 0
    with pytest.raises(ValueError, match=r"T\+1"):
        portfolio.settle_trade("000001.SZ", Side.SELL, 100, Decimal("10"), date(2024, 1, 2), 2, 2)
    portfolio.make_bought_sellable(date(2024, 1, 3))
    sell = portfolio.settle_trade("000001.SZ", Side.SELL, 100, Decimal("11"), date(2024, 1, 3), 3, 3)
    assert sell.tax > 0
    assert portfolio.position("000001.SZ").quantity == 0


def test_insufficient_cash_is_rejected():
    portfolio = Portfolio(Decimal("100"))
    with pytest.raises(ValueError, match="资金不足"):
        portfolio.settle_trade("000001.SZ", Side.BUY, 100, Decimal("2"), date(2024, 1, 2), 1, 1)
