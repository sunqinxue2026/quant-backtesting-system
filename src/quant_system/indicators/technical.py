from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame, short_window: int = 5, long_window: int = 20, volatility_window: int = 20) -> pd.DataFrame:
    if short_window <= 0 or long_window <= 0 or short_window > long_window:
        raise ValueError("均线窗口必须为正，且 short_window <= long_window")
    result = df.copy()
    result["daily_return"] = result["close"].pct_change()
    result["cumulative_return"] = (1 + result["daily_return"].fillna(0)).cumprod() - 1
    result["sma_short"] = result["close"].rolling(short_window, min_periods=short_window).mean()
    result["sma_long"] = result["close"].rolling(long_window, min_periods=long_window).mean()
    result["ema_short"] = result["close"].ewm(span=short_window, adjust=False, min_periods=short_window).mean()
    result["ema_long"] = result["close"].ewm(span=long_window, adjust=False, min_periods=long_window).mean()
    result["rolling_volatility"] = result["daily_return"].rolling(volatility_window, min_periods=volatility_window).std()
    result["volume_ma"] = result["volume"].rolling(short_window, min_periods=short_window).mean()
    return result
