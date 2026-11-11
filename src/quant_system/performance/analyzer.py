from __future__ import annotations

import numpy as np
import pandas as pd
from quant_system.engine.models import Trade


class PerformanceAnalyzer:
    def __init__(self, risk_free_rate: float = 0.03, trading_days: int = 252):
        if trading_days <= 0:
            raise ValueError("trading_days 必须为正数")
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days

    def analyze(self, snapshots: pd.DataFrame, trades: list[Trade] | None = None) -> dict[str, float | None]:
        if snapshots.empty:
            return {}
        values = snapshots["total_value"].astype(float)
        returns = snapshots["daily_return"].astype(float).dropna()
        start, end = values.iloc[0], values.iloc[-1]
        total_return = end / start - 1 if start else 0.0
        dates = pd.to_datetime(snapshots["trade_date"]) if "trade_date" in snapshots else None
        years = max((dates.iloc[-1] - dates.iloc[0]).days / 365.25, 0.0) if dates is not None and len(dates) > 1 else 0.0
        annualized = ((1 + total_return) ** (1 / years) - 1) if years > 0 and total_return > -1 else None
        rf_daily = (1 + self.risk_free_rate) ** (1 / self.trading_days) - 1
        excess = returns - rf_daily
        std = returns.std(ddof=1)
        volatility = float(std * np.sqrt(self.trading_days)) if len(returns) >= 2 else None
        sharpe = float(excess.mean() / std * np.sqrt(self.trading_days)) if len(returns) >= 2 and std > 0 else None
        drawdown = values / values.cummax() - 1
        completed = self._pair_trades(trades or [])
        profits = [item["pnl"] for item in completed]
        wins = [pnl for pnl in profits if pnl > 0]
        losses = [pnl for pnl in profits if pnl < 0]
        return {
            "total_return": float(total_return), "annualized_return": annualized,
            "annualized_volatility": volatility, "max_drawdown": float(drawdown.min()),
            "sharpe_ratio": sharpe, "win_rate": float(len(wins) / len(profits)) if profits else None,
            "profit_loss_ratio": float(np.mean(wins) / abs(np.mean(losses))) if wins and losses else None,
            "trade_count": float(len(trades or [])), "completed_trade_count": float(len(completed)),
            "average_holding_days": float(np.mean([x["holding_days"] for x in completed])) if completed else None,
        }

    @staticmethod
    def _pair_trades(trades: list[Trade]) -> list[dict[str, float]]:
        entries: list[Trade] = []
        completed: list[dict[str, float]] = []
        for trade in trades:
            if trade.side == "BUY":
                entries.append(trade)
            elif trade.side == "SELL":
                remaining = trade.quantity
                while remaining > 0 and entries:
                    entry = entries[0]; quantity = min(remaining, entry.quantity)
                    pnl = (trade.price - entry.price) * quantity - entry.commission - trade.commission - trade.tax
                    completed.append({"pnl": float(pnl), "holding_days": float((trade.trade_date - entry.trade_date).days)})
                    remaining -= quantity
                    entries = entries[1:] if quantity == entry.quantity else [Trade(entry.trade_date, entry.side, entry.quantity - quantity, entry.price, entry.commission, entry.tax)] + entries[1:]
        return completed
