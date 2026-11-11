from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
        signal_map = {pd.Timestamp(row.trade_date): row.side for row in signals.itertuples()}
        trades: list[Trade] = []
        orders: list[Order] = []
        snapshots: list[PortfolioSnapshot] = []
        previous_value = self.portfolio.initial_capital
        for idx, row in data.iterrows():
            current_date = pd.Timestamp(row.trade_date)
            if idx > 0:
                signal_date = pd.Timestamp(data.loc[idx - 1, "trade_date"])
                side = signal_map.get(signal_date)
                if side:
                    desired_qty = self.portfolio.lot_size if side == "BUY" else self.portfolio.position.quantity
                    order = Order(signal_date.date(), current_date.date(), side, desired_qty)
                    orders.append(order)
                    trade = self.portfolio.execute(side, desired_qty, float(row.open))
                    if trade:
                        trades.append(Trade(current_date.date(), trade.side, trade.quantity, trade.price, trade.commission, trade.tax))
            total_value = self.portfolio.cash + self.portfolio.position.quantity * float(row.close)
            daily_return = total_value / previous_value - 1 if previous_value else 0.0
            snapshots.append(PortfolioSnapshot(current_date.date(), self.portfolio.cash, self.portfolio.position.quantity, float(row.close), total_value, daily_return))
            previous_value = total_value
        return BacktestResultData(trades, pd.DataFrame([s.__dict__ for s in snapshots]), orders)
