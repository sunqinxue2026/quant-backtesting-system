from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class Order:
    order_id: int
    symbol: str
    signal_date: date
    execute_date: date | None
    side: Side
    quantity: int
    status: OrderStatus = OrderStatus.PENDING
    reason: str | None = None


@dataclass(frozen=True)
class Trade:
    trade_id: int
    order_id: int
    symbol: str
    trade_date: date
    side: Side
    quantity: int
    price: Decimal
    commission: Decimal
    tax: Decimal
    slippage: Decimal
