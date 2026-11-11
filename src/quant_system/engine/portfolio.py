from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Position, Trade


@dataclass
class Portfolio:
    initial_capital: float
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.0005
    slippage_rate: float = 0.001
    lot_size: int = 100
    cash: float = 0.0
    position: Position | None = None

    def __post_init__(self) -> None:
        if self.initial_capital <= 0 or self.lot_size <= 0:
            raise ValueError("初始资金和交易单位必须为正")
        for name, value in {
            "commission_rate": self.commission_rate,
            "stamp_tax_rate": self.stamp_tax_rate,
            "slippage_rate": self.slippage_rate,
        }.items():
            if value < 0:
                raise ValueError(f"{name} 不能为负数")
        self.cash = float(self.initial_capital)
        self.position = Position()

    def execute(self, side: str, quantity: int, price: float, trade_date: date | None = None) -> Trade | None:
        """按成交日和开盘价执行订单，返回实际成交记录。"""
        if quantity <= 0 or price <= 0:
            return None
        side = side.upper()
        quantity = (quantity // self.lot_size) * self.lot_size
        if quantity == 0:
            return None
        fill_price = price * (1 + self.slippage_rate if side == "BUY" else 1 - self.slippage_rate)
        if side == "BUY":
            affordable = int(self.cash / (fill_price * (1 + self.commission_rate)))
            quantity = min(quantity, (affordable // self.lot_size) * self.lot_size)
            if quantity <= 0:
                return None
            gross = fill_price * quantity
            commission = gross * self.commission_rate
            tax = 0.0
            self.cash -= gross + commission
            old_qty = self.position.quantity
            new_qty = old_qty + quantity
            self.position.average_price = ((self.position.average_price * old_qty) + gross) / new_qty
            self.position.quantity = new_qty
        elif side == "SELL":
            quantity = min(quantity, self.position.quantity)
            quantity = (quantity // self.lot_size) * self.lot_size
            if quantity <= 0:
                return None
            gross = fill_price * quantity
            commission = gross * self.commission_rate
            tax = gross * self.stamp_tax_rate
            self.cash += gross - commission - tax
            self.position.quantity -= quantity
            if self.position.quantity == 0:
                self.position.average_price = 0.0
        else:
            raise ValueError(f"不支持的交易方向: {side}")
        return Trade(trade_date or date.today(), side, quantity, fill_price, commission, tax)
