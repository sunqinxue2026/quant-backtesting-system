from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Position, PositionLot, Trade


@dataclass
class Portfolio:
    initial_capital: float
    commission_rate: float = 0.0003
    min_commission: float = 0.0
    stamp_tax_rate: float = 0.0005
    slippage_bps: float = 10.0
    lot_size: int = 100
    # 兼容旧版调用；传入后按比例转换为基点
    slippage_rate: float | None = None
    cash: float = 0.0
    position: Position | None = None

    def __post_init__(self) -> None:
        if self.initial_capital <= 0 or self.lot_size <= 0:
            raise ValueError("初始资金和交易单位必须为正")
        for name, value in {"commission_rate": self.commission_rate, "min_commission": self.min_commission, "stamp_tax_rate": self.stamp_tax_rate, "slippage_bps": self.slippage_bps}.items():
            if value < 0:
                raise ValueError(f"{name} 不能为负数")
        if self.slippage_rate is not None:
            if self.slippage_rate < 0:
                raise ValueError("slippage_rate 不能为负数")
            self.slippage_bps = self.slippage_rate * 10000
        self.cash = float(self.initial_capital)
        self.position = Position()

    @property
    def effective_slippage_rate(self) -> float:
        return self.slippage_bps / 10000

    def execute(self, side: str, quantity: int, price: float, trade_date: date | None = None) -> Trade | None:
        if quantity <= 0 or price <= 0:
            return None
        side = side.upper()
        quantity = (quantity // self.lot_size) * self.lot_size
        if quantity == 0:
            return None
        fill_price = price * (1 + self.effective_slippage_rate if side == "BUY" else 1 - self.effective_slippage_rate)
        if side == "BUY":
            affordable = int(self.cash / (fill_price + self.commission_rate * fill_price))
            quantity = min(quantity, (affordable // self.lot_size) * self.lot_size)
            if quantity <= 0:
                return None
            gross = fill_price * quantity
            commission = max(gross * self.commission_rate, self.min_commission)
            self.cash -= gross + commission
            old_qty = self.position.quantity
            self.position.quantity += quantity
            self.position.average_price = ((self.position.average_price * old_qty) + gross) / self.position.quantity
            self.position.lots.append(PositionLot(quantity, fill_price, trade_date or date.today()))
            tax = 0.0
        elif side == "SELL":
            available = sum(lot.quantity for lot in self.position.lots if lot.buy_date < (trade_date or date.today()))
            quantity = min(quantity, available)
            quantity = (quantity // self.lot_size) * self.lot_size
            if quantity <= 0:
                return None
            gross = fill_price * quantity
            commission = max(gross * self.commission_rate, self.min_commission)
            tax = gross * self.stamp_tax_rate
            self.cash += gross - commission - tax
            self.position.quantity -= quantity
            remaining = quantity
            while remaining > 0 and self.position.lots:
                lot = self.position.lots[0]
                if lot.buy_date >= (trade_date or date.today()):
                    break
                used = min(remaining, lot.quantity)
                lot.quantity -= used
                remaining -= used
                if lot.quantity == 0:
                    self.position.lots.pop(0)
            if self.position.quantity == 0:
                self.position.average_price = 0.0
        else:
            raise ValueError(f"不支持的交易方向: {side}")
        return Trade(trade_date or date.today(), side, quantity, fill_price, commission, tax)
