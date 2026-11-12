from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = {"symbol", "trade_date", "close", "volume"}


def _validate_window(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} 必须为正整数")


def _validate_frame(data: pd.DataFrame) -> None:
    missing = sorted(_REQUIRED_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(f"指标计算缺少字段: {', '.join(missing)}")


def add_indicators(
    data: pd.DataFrame,
    *,
    short_window: int = 5,
    long_window: int = 20,
    volatility_window: int = 20,
    volume_window: int = 20,
    annualization_days: int = 252,
) -> pd.DataFrame:
    """为行情数据增加日收益率、均线和波动率指标。

    指标只使用当前行及其之前的数据；窗口不足时保留 NaN，不填充为 0。
    多股票数据按 symbol 分组计算，输出按 symbol、trade_date 排序。
    """
    _validate_frame(data)
    for name, value in (
        ("short_window", short_window),
        ("long_window", long_window),
        ("volatility_window", volatility_window),
        ("volume_window", volume_window),
        ("annualization_days", annualization_days),
    ):
        _validate_window(name, value)
    if short_window >= long_window:
        raise ValueError("short_window 必须小于 long_window")

    result = data.copy(deep=True)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="raise").dt.date
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["volume"] = pd.to_numeric(result["volume"], errors="coerce")
    result = result.sort_values(["symbol", "trade_date"], kind="mergesort").reset_index(drop=True)

    grouped_close = result.groupby("symbol", sort=False)["close"]
    grouped_volume = result.groupby("symbol", sort=False)["volume"]
    result["daily_return"] = grouped_close.pct_change(fill_method=None)
    result["cumulative_return"] = grouped_close.transform(lambda series: series / series.iloc[0] - 1 if len(series) and series.iloc[0] else np.nan)
    result["sma_short"] = grouped_close.transform(lambda series: series.rolling(short_window, min_periods=short_window).mean())
    result["sma_long"] = grouped_close.transform(lambda series: series.rolling(long_window, min_periods=long_window).mean())
    result["ema_short"] = grouped_close.transform(lambda series: series.ewm(span=short_window, min_periods=short_window, adjust=False).mean())
    result["ema_long"] = grouped_close.transform(lambda series: series.ewm(span=long_window, min_periods=long_window, adjust=False).mean())
    result["rolling_volatility"] = grouped_close.transform(
        lambda series: series.pct_change(fill_method=None).rolling(volatility_window, min_periods=volatility_window).std(ddof=1)
    )
    result["annualized_rolling_volatility"] = result["rolling_volatility"] * np.sqrt(annualization_days)
    result["volume_ma"] = grouped_volume.transform(lambda series: series.rolling(volume_window, min_periods=volume_window).mean())
    return result
