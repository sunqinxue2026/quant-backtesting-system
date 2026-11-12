from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_system.strategies import DualMovingAverageStrategy


def indicator_frame(short_values: list[float | None], long_values: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["000001.SZ"] * len(short_values),
            "trade_date": pd.date_range("2024-01-01", periods=len(short_values)),
            "sma_short": short_values,
            "sma_long": long_values,
        }
    )


def test_upward_cross_generates_buy_signal():
    result = DualMovingAverageStrategy(2, 3).generate_signals(
        indicator_frame([None, 9, 11, 12], [None, 10, 10, 11])
    )
    assert result.to_dict("records") == [
        {"symbol": "000001.SZ", "trade_date": date(2024, 1, 3), "side": "BUY", "sma_short": 11.0, "sma_long": 10.0}
    ]


def test_downward_cross_generates_sell_signal():
    result = DualMovingAverageStrategy(2, 3).generate_signals(
        indicator_frame([None, 11, 9, 8], [None, 10, 10, 9])
    )
    assert result.to_dict("records") == [
        {"symbol": "000001.SZ", "trade_date": date(2024, 1, 3), "side": "SELL", "sma_short": 9.0, "sma_long": 10.0}
    ]


def test_equal_previous_values_then_cross_generates_signal():
    result = DualMovingAverageStrategy(2, 3).generate_signals(
        indicator_frame([None, 10, 12], [None, 10, 11])
    )
    assert result.iloc[0]["side"] == "BUY"


def test_missing_window_values_do_not_generate_signal():
    result = DualMovingAverageStrategy(2, 3).generate_signals(
        indicator_frame([None, None, 10], [None, None, 9])
    )
    assert result.empty


def test_no_cross_has_no_signal_and_input_is_not_mutated():
    source = indicator_frame([None, 9, 10, 11], [None, 10, 11, 12])
    original = source.copy(deep=True)
    result = DualMovingAverageStrategy(2, 3).generate_signals(source)
    assert result.empty
    assert source.equals(original)


def test_future_rows_do_not_change_previous_signals():
    strategy = DualMovingAverageStrategy(2, 3)
    source = indicator_frame([None, 9, 11, 10], [None, 10, 10, 10])
    extended = pd.concat(
        [source, indicator_frame([9, 12], [10, 10]).assign(trade_date=pd.date_range("2024-01-05", periods=2))],
        ignore_index=True,
    )
    first = strategy.generate_signals(source)
    second = strategy.generate_signals(extended)
    assert first.to_dict("records") == second[second["trade_date"] <= date(2024, 1, 4)].to_dict("records")


@pytest.mark.parametrize("short_window,long_window", [(0, 3), (3, 3), (4, 3)])
def test_invalid_strategy_parameters_are_rejected(short_window, long_window):
    with pytest.raises(ValueError):
        DualMovingAverageStrategy(short_window, long_window)


def test_missing_strategy_column_is_rejected():
    with pytest.raises(ValueError, match="缺少字段"):
        DualMovingAverageStrategy().generate_signals(pd.DataFrame({"symbol": ["000001.SZ"]}))
