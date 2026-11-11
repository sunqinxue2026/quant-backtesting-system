from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from quant_system.engine.models import Order, PortfolioSnapshot, Trade
from quant_system.engine.portfolio import Portfolio


@dataclass
class BacktestResultData:
    trades: list[Trade]
    snapshots: pd.DataFrame
    orders: list[Order]


class BacktestEngine:
    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio

    def run(self, market_data: pd.DataFrame, signals: pd.DataFrame) -> BacktestResultData:
        data = market_data.sort_values("trade_date").reset_index(drop=True).copy()
        data["trade_date"] = pd.to_datetime(data["trade_date"])
        signals = signals.copy()
        if not signals.empty:
            signals["trade_date"] = pd.to_datetime(signals["trade_date"])
        signal_map = {
            pd.Timestamp(row.trade_date): row.side
            for row in signals.itertuples()
        }
        trades: list[Trade] = []
        orders: list[Order] = []
        snapshots: list[PortfolioSnapshot] = []
        previous_value = self.portfolio.initial_capital

        for idx, row in data.iterrows():
            current_date = pd.Timestamp(row.trade_date)
            if idx > 0:
                signal_date = pd.Timestamp(data.loc[idx - 1, "trade_date"])
                side = signal_map.get(signal_date)
                if side in {"BUY", "SELL"}:
                    desired_qty = self.portfolio.lot_size if side == "BUY" else self.portfolio.position.quantity
                    trade = self.portfolio.execute(side, desired_qty, float(row.open), current_date.date())
                    status = "FILLED" if trade else "REJECTED"
                    orders.append(Order(signal_date.date(), current_date.date(), side, desired_qty, status))
                    if trade:
                        trades.append(trade)

            total_value = self.portfolio.cash + self.portfolio.position.quantity * float(row.close)
            daily_return = total_value / previous_value - 1 if previous_value else 0.0
            snapshots.append(
                PortfolioSnapshot(
                    current_date.date(), self.portfolio.cash, self.portfolio.position.quantity,
                    float(row.close), total_value, daily_return,
                )
            )
            previous_value = total_value
        return BacktestResultData(trades, pd.DataFrame([s.__dict__ for s in snapshots]), orders)
