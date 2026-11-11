from __future__ import annotations

from datetime import date
import numpy as np
import pandas as pd

from quant_system.engine.models import Trade


class PerformanceAnalyzer:
    def __init__(self, risk_free_rate: float = 0.03, trading_days: int = 252):
        if trading_days <= 0:
            raise ValueError("trading_days 必须为正数")
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days

    def analyze(self, snapshots: pd.DataFrame, trades: list[Trade] | None = None) -> dict[str, float]:
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
        std = returns.std(ddof=1)
        volatility = float(std * np.sqrt(self.trading_days)) if len(returns) > 1 else 0.0
        sharpe = float(excess.mean() / std * np.sqrt(self.trading_days)) if len(returns) > 1 and std > 0 else 0.0
        peak = values.cummax()
        drawdown = values / peak - 1
        max_drawdown = float(drawdown.min())

        completed = self._pair_trades(trades or [])
        profits = [item["pnl"] for item in completed]
        wins = [pnl for pnl in profits if pnl > 0]
        losses = [pnl for pnl in profits if pnl < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        holding_days = [item["holding_days"] for item in completed]
        return {
            "total_return": float(total_return),
            "annualized_return": float(annualized),
            "annualized_volatility": volatility,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "win_rate": float(len(wins) / len(profits)) if profits else 0.0,
            "profit_loss_ratio": float(gross_profit / gross_loss) if gross_loss else 0.0,
            "trade_count": float(len(trades or [])),
            "completed_trade_count": float(len(completed)),
            "average_holding_days": float(np.mean(holding_days)) if holding_days else 0.0,
        }

    @staticmethod
    def _pair_trades(trades: list[Trade]) -> list[dict[str, float]]:
        """FIFO 配对多头成交；未平仓买入不计入胜率和盈亏比。"""
        entries: list[Trade] = []
        completed: list[dict[str, float]] = []
        for trade in trades:
            if trade.side == "BUY":
                entries.append(trade)
            elif trade.side == "SELL":
                remaining = trade.quantity
                while remaining > 0 and entries:
                    entry = entries[0]
                    quantity = min(remaining, entry.quantity)
                    pnl = (trade.price - entry.price) * quantity - entry.commission - trade.commission - trade.tax
                    completed.append({
                        "pnl": float(pnl),
                        "holding_days": float((trade.trade_date - entry.trade_date).days),
                    })
                    remaining -= quantity
                    if quantity == entry.quantity:
                        entries.pop(0)
                    else:
                        entries[0] = Trade(entry.trade_date, entry.side, entry.quantity - quantity, entry.price, entry.commission, entry.tax)
        return completed
