from decimal import Decimal

import pandas as pd

from quant_system.engine import BacktestEngine, CostModel
from quant_system.strategies import DualMovingAverageStrategy


def frame():
    return pd.DataFrame(
        {
            "symbol": ["000001.SZ"] * 5,
            "trade_date": pd.date_range("2024-01-01", periods=5),
            "open": [10, 10, 12, 13, 9],
            "close": [10, 11, 12, 10, 9],
            "sma_short": [None, 9, 11, 9, 9],
            "sma_long": [None, 10, 10, 10, 10],
        }
    )


def test_signal_at_close_executes_next_day_open_and_snapshots_are_daily():
    engine = BacktestEngine(DualMovingAverageStrategy(2, 3), Decimal("10000"), CostModel(slippage_bps=0, commission_rate=0, minimum_commission=0, stamp_tax_rate=0), order_quantity=100)
    result = engine.run(frame())
    assert [(order.signal_date, order.execute_date, order.status.value) for order in result.orders] == [
        (pd.Timestamp("2024-01-03").date(), pd.Timestamp("2024-01-04").date(), "FILLED"),
        (pd.Timestamp("2024-01-04").date(), pd.Timestamp("2024-01-05").date(), "FILLED"),
    ]
    assert result.trades[0].trade_date == pd.Timestamp("2024-01-04").date()
    assert result.trades[0].price == Decimal("13")
    assert result.trades[1].price == Decimal("9")
    assert result.snapshots[2].position_quantity == 0
    assert result.snapshots[3].position_quantity == 100
    assert result.snapshots[4].position_quantity == 0
    assert result.final_cash == Decimal("9600")
    assert result.final_value == Decimal("9600")


def test_last_day_signal_expires_and_zero_quantity_is_rejected():
    data = frame().iloc[:4].copy()
    data.loc[3, "sma_short"] = 9
    data.loc[3, "sma_long"] = 10
    engine = BacktestEngine(DualMovingAverageStrategy(2, 3), Decimal("1000"), order_quantity=0)
    result = engine.run(data)
    assert any(order.status.value == "EXPIRED" for order in result.orders)


def test_insufficient_cash_creates_rejected_order():
    engine = BacktestEngine(DualMovingAverageStrategy(2, 3), Decimal("100"), order_quantity=100)
    result = engine.run(frame())
    assert any(order.status.value == "REJECTED" and "资金不足" in (order.reason or "") for order in result.orders)
    assert not result.trades
