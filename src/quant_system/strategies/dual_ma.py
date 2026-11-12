from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class Signal:
    """收盘后生成的策略信号；成交日期由后续订单模块决定。"""

    symbol: str
    signal_date: date
    side: str
    short_value: float
    long_value: float


class DualMovingAverageStrategy:
    """基于短、长 SMA 交叉生成 BUY/SELL 信号。"""

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        if not isinstance(short_window, int) or isinstance(short_window, bool) or short_window <= 0:
            raise ValueError("short_window 必须为正整数")
        if not isinstance(long_window, int) or isinstance(long_window, bool) or long_window <= 0:
            raise ValueError("long_window 必须为正整数")
        if short_window >= long_window:
            raise ValueError("short_window 必须小于 long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.short_column = "sma_short"
        self.long_column = "sma_long"

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """生成交叉信号，只使用当前行和前一行指标。"""
        required = {"symbol", "trade_date", self.short_column, self.long_column}
        missing = sorted(required - set(data.columns))
        if missing:
            raise ValueError(f"策略输入缺少字段: {', '.join(missing)}")
        frame = data.copy(deep=True)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.date
        frame = frame.sort_values(["symbol", "trade_date"], kind="mergesort").reset_index(drop=True)
        signals: list[Signal] = []
        for symbol, group in frame.groupby("symbol", sort=False):
            previous_short = group[self.short_column].shift(1)
            previous_long = group[self.long_column].shift(1)
            current_short = group[self.short_column]
            current_long = group[self.long_column]
            buy = current_short.gt(current_long) & previous_short.le(previous_long)
            sell = current_short.lt(current_long) & previous_short.ge(previous_long)
            for index in group.index[buy.fillna(False) | sell.fillna(False)]:
                side = "BUY" if bool(buy.loc[index]) else "SELL"
                signals.append(
                    Signal(
                        symbol=str(symbol),
                        signal_date=frame.loc[index, "trade_date"],
                        side=side,
                        short_value=float(frame.loc[index, self.short_column]),
                        long_value=float(frame.loc[index, self.long_column]),
                    )
                )
        return pd.DataFrame(
            [
                {
                    "symbol": item.symbol,
                    "trade_date": item.signal_date,
                    "side": item.side,
                    "sma_short": item.short_value,
                    "sma_long": item.long_value,
                }
                for item in signals
            ],
            columns=["symbol", "trade_date", "side", "sma_short", "sma_long"],
        )
