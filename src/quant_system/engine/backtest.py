from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol
import logging
import numpy as np

import pandas as pd

from ..strategies.dual_ma import DualMovingAverageStrategy
from .models import Order, OrderStatus, Side, Trade
from .portfolio import CostModel, Portfolio


logger = logging.getLogger(__name__)


class Strategy(Protocol):
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame: ...


@dataclass(frozen=True)
class Snapshot:
    trade_date: date
    cash: Decimal
    position_quantity: int
    close_price: Decimal
    total_value: Decimal
    daily_return: Decimal | None


@dataclass(frozen=True)
class BacktestResult:
    orders: list[Order]
    trades: list[Trade]
    snapshots: list[Snapshot]
    final_cash: Decimal
    final_position: int
    final_value: Decimal


class BacktestEngine:
    """日频回测引擎：t日收盘产生信号，t+1日开盘执行。"""

    def __init__(
        self,
        strategy: Strategy,
        initial_cash: Decimal,
        cost_model: CostModel | None = None,
        order_quantity: int | None = None,
    ) -> None:
        if order_quantity is not None and (isinstance(order_quantity, bool) or not isinstance(order_quantity, int) or order_quantity < 0):
            raise ValueError("订单数量必须为非负整数或None")
        self.initial_cash = Decimal(str(initial_cash))
        self.strategy = strategy
        self.portfolio = Portfolio(initial_cash, cost_model)
        self.order_quantity = order_quantity
        self._order_id = 0
        self._trade_id = 0

    def run(self, data: pd.DataFrame) -> BacktestResult:
        required = {"symbol", "trade_date", "open", "close", "sma_short", "sma_long"}
        missing = sorted(required - set(data.columns))
        if missing:
            raise ValueError(f"回测输入缺少字段: {', '.join(missing)}")
        self.portfolio = Portfolio(self.initial_cash, self.portfolio.cost_model)
        self._order_id = self._trade_id = 0
        frame = data.copy(deep=True)
        if frame.empty:
            raise ValueError("回测行情不能为空")
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.date
        for column in ("open", "close"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame["trade_date"].isna().any() or frame.duplicated(["symbol", "trade_date"]).any():
            raise ValueError("日期无效或行情重复")
        if not np.isfinite(frame["close"]).all() or (frame["close"] <= 0).any():
            raise ValueError("回测输入存在无效收盘价")
        frame = frame.sort_values(["trade_date", "symbol"], kind="mergesort").reset_index(drop=True)
        if frame["symbol"].nunique() != 1:
            raise ValueError("第五阶段第一版只支持单股票")

        signal_frame = self.strategy.generate_signals(frame)
        if signal_frame.duplicated(["symbol", "trade_date"]).any():
            raise ValueError("同股票同日存在重复交易信号")
        signal_by_date = {row.trade_date: row for row in signal_frame.itertuples(index=False)}
        dates = list(frame["trade_date"].drop_duplicates())
        rows_by_date = {trade_date: group.iloc[0] for trade_date, group in frame.groupby("trade_date", sort=True)}
        pending: list[Order] = []
        orders: list[Order] = []
        trades: list[Trade] = []
        snapshots: list[Snapshot] = []
        previous_value: Decimal | None = None

        for index, trade_date in enumerate(dates):
            self.portfolio.make_bought_sellable(trade_date)
            row = rows_by_date[trade_date]
            today_price = Decimal(str(row["open"]))
            for order in pending:
                if order.execute_date != trade_date:
                    continue
                filled = self._execute(order, today_price, trade_date)
                orders.append(filled[0])
                if filled[1] is not None:
                    trades.append(filled[1])
            pending = [order for order in pending if order.execute_date != trade_date]

            close_prices = {str(row["symbol"]): Decimal(str(row["close"]))}
            total_value = self.portfolio.total_value(close_prices)
            daily_return = None if previous_value in (None, Decimal("0")) else (total_value / previous_value - Decimal("1"))
            snapshots.append(Snapshot(trade_date, self.portfolio.cash, self.portfolio.position(str(row["symbol"])).quantity, close_prices[str(row["symbol"])], total_value, daily_return))
            previous_value = total_value

            signal = signal_by_date.get(trade_date)
            if signal is None:
                continue
            next_date = dates[index + 1] if index + 1 < len(dates) else None
            side = Side(signal.side)
            quantity = self._quantity(side, str(row["symbol"]), today_price)
            self._order_id += 1
            if next_date is None:
                orders.append(Order(self._order_id, str(row["symbol"]), trade_date, None, side, quantity, OrderStatus.EXPIRED, "最后交易日没有下一可交易日"))
            elif quantity == 0:
                orders.append(Order(self._order_id, str(row["symbol"]), trade_date, next_date, side, quantity, OrderStatus.REJECTED, "订单数量为零或不满足交易单位"))
            else:
                pending.append(Order(self._order_id, str(row["symbol"]), trade_date, next_date, side, quantity))

        logger.info("回测完成 orders=%d trades=%d snapshots=%d", len(orders), len(trades), len(snapshots))
        return BacktestResult(orders, trades, snapshots, self.portfolio.cash, self.portfolio.position(str(frame.iloc[0]["symbol"])).quantity, snapshots[-1].total_value)

    def _quantity(self, side: Side, symbol: str, price: Decimal) -> int:
        position = self.portfolio.position(symbol)
        if side is Side.SELL:
            return position.quantity
        if position.quantity:
            return 0
        if self.order_quantity is not None:
            return self.order_quantity
        return -1  # 自动仓位在执行日按实际开盘价计算

    def _execute(self, order: Order, open_price: Decimal, trade_date: date) -> tuple[Order, Trade | None]:
        if order.quantity == -1:
            if not open_price.is_finite() or open_price <= 0:
                return Order(order.order_id, order.symbol, order.signal_date, order.execute_date, order.side, 0, OrderStatus.REJECTED, "无效开盘价"), None
            lot = self.portfolio.cost_model.lot_size
            rate = self.portfolio.cost_model.slippage_bps / Decimal("10000")
            high = int(self.portfolio.cash / (open_price * (1 + rate))) // lot
            low = 0
            while low < high:
                mid = (low + high + 1) // 2
                if self.portfolio.cash + self.portfolio.estimate(Side.BUY, mid * lot, open_price).total_cash_change >= 0:
                    low = mid
                else:
                    high = mid - 1
            order = Order(order.order_id, order.symbol, order.signal_date, order.execute_date, order.side, low * lot)
            if order.quantity == 0:
                return Order(order.order_id, order.symbol, order.signal_date, order.execute_date, order.side, 0, OrderStatus.REJECTED, "资金不足以买入一手"), None
        try:
            self._trade_id += 1
            trade = self.portfolio.settle_trade(order.symbol, order.side, order.quantity, open_price, trade_date, order.order_id, self._trade_id)
        except ValueError as exc:
            return Order(order.order_id, order.symbol, order.signal_date, order.execute_date, order.side, order.quantity, OrderStatus.REJECTED, str(exc)), None
        return Order(order.order_id, order.symbol, order.signal_date, order.execute_date, order.side, order.quantity, OrderStatus.FILLED), trade
