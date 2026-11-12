from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_system.indicators import add_indicators


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["000001.SZ"] * 5,
            "trade_date": pd.date_range("2024-01-01", periods=5),
            "close": [10.0, 11.0, 12.0, 10.0, 11.0],
            "volume": [100, 200, 300, 400, 500],
        }
    )


def test_returns_sma_ema_volatility_and_volume_ma_match_manual_values():
    source = frame()
    result = add_indicators(
        source,
        short_window=2,
        long_window=3,
        volatility_window=2,
        volume_window=3,
    )

    assert result["daily_return"].iloc[0] != result["daily_return"].iloc[0]
    assert result["daily_return"].iloc[1] == pytest.approx(0.1)
    assert result["cumulative_return"].iloc[-1] == pytest.approx(0.1)
    assert result["sma_short"].iloc[1] == pytest.approx(10.5)
    assert result["sma_long"].iloc[2] == pytest.approx(11.0)
    expected_ema_short = 2 / 3 * 11 + 1 / 3 * 10
    assert result["ema_short"].iloc[2] == pytest.approx(2 / 3 * 12 + 1 / 3 * expected_ema_short)
    returns = pd.Series([0.1, 12 / 11 - 1])
    assert result["rolling_volatility"].iloc[2] == pytest.approx(returns.std(ddof=1))
    assert result["volume_ma"].iloc[2] == pytest.approx(200.0)
    assert result["annualized_rolling_volatility"].iloc[2] == pytest.approx(result["rolling_volatility"].iloc[2] * np.sqrt(252))


def test_window_insufficient_keeps_nan_and_does_not_mutate_input():
    source = frame()
    original = source.copy(deep=True)
    result = add_indicators(source, short_window=2, long_window=4, volatility_window=3, volume_window=4)

    assert source.equals(original)
    assert pd.isna(result["sma_long"].iloc[0])
    assert pd.isna(result["sma_long"].iloc[2])
    assert pd.isna(result["volume_ma"].iloc[2])
    assert pd.isna(result["rolling_volatility"].iloc[2])


def test_multiple_symbols_are_calculated_independently():
    source = pd.concat(
        [frame(), frame().assign(symbol="600000.SH", close=[20.0, 22.0, 24.0, 20.0, 22.0])],
        ignore_index=True,
    ).sample(frac=1, random_state=7)
    result = add_indicators(source, short_window=2, long_window=3, volatility_window=2, volume_window=3)

    second = result[result["symbol"] == "600000.SH"].sort_values("trade_date")
    assert second.iloc[0]["daily_return"] != second.iloc[0]["daily_return"]
    assert second.iloc[2]["sma_long"] == pytest.approx(22.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"short_window": 0},
        {"long_window": 1, "short_window": 1},
        {"volatility_window": 0},
        {"volume_window": -1},
        {"annualization_days": 0},
    ],
)
def test_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        add_indicators(frame(), **kwargs)


def test_missing_required_column_is_rejected():
    with pytest.raises(ValueError, match="缺少字段"):
        add_indicators(frame().drop(columns=["volume"]))
