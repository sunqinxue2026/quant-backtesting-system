from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Order:
    signal_date: date
    execute_date: date
    side: str
    quantity: int
    status: str = "PENDING"
    reason: str = ""


@dataclass(frozen=True)
class Trade:
    trade_date: date
    side: str
    quantity: int
    price: float
    commission: float
    tax: float

    @property
    def net_cash_flow(self) -> float:
        gross = self.price * self.quantity
        costs = self.commission + self.tax
        return -gross - costs if self.side == "BUY" else gross - costs


@dataclass
class PositionLot:
    quantity: int
    average_price: float
    buy_date: date


@dataclass
class Position:
    quantity: int = 0
    average_price: float = 0.0
    lots: list[PositionLot] | None = None

    def __post_init__(self) -> None:
        if self.lots is None:
            self.lots = []


@dataclass(frozen=True)
class PortfolioSnapshot:
    trade_date: date
    cash: float
    position_quantity: int
    close_price: float
    total_value: float
    daily_return: float
