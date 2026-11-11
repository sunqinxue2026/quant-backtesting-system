from __future__ import annotations

import numpy as np
import pandas as pd

class PerformanceAnalyzer:
    def __init__(self, risk_free_rate: float = 0.03, trading_days: int = 252):
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days

    def analyze(self, snapshots: pd.DataFrame, trades: list | None = None) -> dict[str, float]:
        if snapshots.empty:
            return {}
        values = snapshots["total_value"].astype(float)
        returns = snapshots["daily_return"].astype(float)
        start, end = values.iloc[0], values.iloc[-1]
        total_return = end / start - 1 if start else 0.0
        years = max(len(values) / self.trading_days, 1 / self.trading_days)
        annualized = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0
        rf_daily = (1 + self.risk_free_rate) ** (1 / self.trading_days) - 1
        excess = returns - rf_daily
        volatility = float(returns.std(ddof=1) * np.sqrt(self.trading_days)) if len(returns) > 1 else 0.0
        sharpe = float(excess.mean() / returns.std(ddof=1) * np.sqrt(self.trading_days)) if len(returns) > 1 and returns.std(ddof=1) > 0 else 0.0
        peak = values.cummax()
        drawdown = values / peak - 1
        max_drawdown = float(drawdown.min())
        trade_list = trades or []
        sells = [t for t in trade_list if t.side == "SELL"]
        wins = sum(1 for t in sells if t.price > 0)
        return {"total_return": float(total_return), "annualized_return": float(annualized), "annualized_volatility": volatility, "max_drawdown": max_drawdown, "sharpe_ratio": sharpe, "win_rate": float(wins / len(sells)) if sells else 0.0, "trade_count": float(len(trade_list)), "completed_sell_count": float(len(sells))}
