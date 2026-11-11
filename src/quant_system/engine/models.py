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

@dataclass(frozen=True)
class Trade:
    trade_date: date
    side: str
    quantity: int
    price: float
    commission: float
    tax: float

@dataclass
class Position:
    quantity: int = 0
    average_price: float = 0.0

@dataclass(frozen=True)
class PortfolioSnapshot:
    trade_date: date
    cash: float
    position_quantity: int
    close_price: float
    total_value: float
    daily_return: float
