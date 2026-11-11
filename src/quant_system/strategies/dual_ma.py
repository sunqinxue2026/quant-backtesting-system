from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class Signal:
    symbol: str
    signal_date: pd.Timestamp
    side: str
    short_value: float
    long_value: float

class DualMovingAverageStrategy:
    def __init__(self, short_window: int = 5, long_window: int = 20):
        if short_window <= 0 or long_window <= short_window:
            raise ValueError("必须满足 0 < short_window < long_window")
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        required = {"symbol", "trade_date", "sma_short", "sma_long"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"缺少策略字段: {sorted(missing)}")
        work = df.sort_values("trade_date").reset_index(drop=True).copy()
        cross_up = (work["sma_short"] > work["sma_long"]) & (work["sma_short"].shift(1) <= work["sma_long"].shift(1))
        cross_down = (work["sma_short"] < work["sma_long"]) & (work["sma_short"].shift(1) >= work["sma_long"].shift(1))
        side = pd.Series(pd.NA, index=work.index, dtype="string")
        side.loc[cross_up] = "BUY"
        side.loc[cross_down] = "SELL"
        result = work.loc[side.notna(), ["symbol", "trade_date", "sma_short", "sma_long"]].copy()
        result["side"] = side.loc[side.notna()].astype(str).to_numpy()
        return result.reset_index(drop=True)
