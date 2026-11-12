from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN

from .models import Side, Trade


MONEY_QUANT = Decimal("0.01")


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    sellable_quantity: int = 0
    average_cost: Decimal = Decimal("0")
    last_buy_date: date | None = None


@dataclass(frozen=True)
class CostModel:
    commission_rate: Decimal = Decimal("0.0003")
    minimum_commission: Decimal = Decimal("5")
    stamp_tax_rate: Decimal = Decimal("0.0005")
    slippage_bps: Decimal = Decimal("5")
    lot_size: int = 100

    def __post_init__(self) -> None:
        for name in ("commission_rate", "minimum_commission", "stamp_tax_rate", "slippage_bps"):
            value = Decimal(str(getattr(self, name)))
            if not value.is_finite():
                raise ValueError("成本参数必须是有限数值")
            object.__setattr__(self, name, value)
        if isinstance(self.lot_size, bool) or not isinstance(self.lot_size, int):
            raise ValueError("交易单位必须为正整数")
        if self.slippage_bps >= 10000:
            raise ValueError("滑点必须小于10000基点")
        if self.commission_rate < 0 or self.minimum_commission < 0 or self.stamp_tax_rate < 0:
            raise ValueError("交易成本参数不能为负数")
        if self.slippage_bps < 0 or self.lot_size <= 0:
            raise ValueError("滑点不能为负数，交易单位必须为正整数")


@dataclass(frozen=True)
class FillEstimate:
    execution_price: Decimal
    commission: Decimal
    tax: Decimal
    slippage: Decimal
    total_cash_change: Decimal


class Portfolio:
    """单股票、现货、只做多账户；买入当日不可卖出。"""

    def __init__(self, initial_cash: Decimal, cost_model: CostModel | None = None) -> None:
        initial_cash = Decimal(str(initial_cash))
        if not initial_cash.is_finite() or initial_cash <= 0:
            raise ValueError("初始资金必须大于零")
        self.initial_cash = initial_cash.quantize(MONEY_QUANT)
        self.cash = self.initial_cash
        self.cost_model = cost_model or CostModel()
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []

    def position(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position(symbol=symbol))

    def estimate(self, side: Side, quantity: int, open_price: Decimal) -> FillEstimate:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("成交数量必须大于零")
        open_price = Decimal(str(open_price))
        if not open_price.is_finite() or open_price <= 0:
            raise ValueError("成交价格必须大于零")
        rate = self.cost_model.slippage_bps / Decimal("10000")
        slippage = (open_price * rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        execution_price = open_price + slippage if side is Side.BUY else open_price - slippage
        turnover = (execution_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        commission = max(
            (turnover * self.cost_model.commission_rate).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN),
            self.cost_model.minimum_commission if turnover > 0 else Decimal("0"),
        )
        tax = (turnover * self.cost_model.stamp_tax_rate).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN) if side is Side.SELL else Decimal("0")
        cash_change = -(turnover + commission + tax) if side is Side.BUY else turnover - commission - tax
        return FillEstimate(execution_price, commission, tax, slippage, cash_change)

    def can_sell(self, symbol: str, quantity: int) -> bool:
        return quantity > 0 and self.position(symbol).sellable_quantity >= quantity

    def settle_trade(self, symbol: str, side: Side, quantity: int, price: Decimal, trade_date: date, order_id: int, trade_id: int) -> Trade:
        if not isinstance(side, Side):
            raise ValueError("成交方向必须是Side")
        estimate = self.estimate(side, quantity, price)
        if side is Side.BUY and quantity % self.cost_model.lot_size:
            raise ValueError("买入数量不满足整手交易单位")
        if side is Side.BUY and self.position(symbol).quantity:
            raise ValueError("第一版不允许加仓")
        if side is Side.BUY and self.cash + estimate.total_cash_change < 0:
            raise ValueError("资金不足")
        if side is Side.SELL and not self.can_sell(symbol, quantity):
            raise ValueError("可卖数量不足或违反T+1")
        position = self.position(symbol)
        trade = Trade(trade_id, order_id, symbol, trade_date, side, quantity, estimate.execution_price, estimate.commission, estimate.tax, estimate.slippage)
        self.cash = (self.cash + estimate.total_cash_change).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)
        turnover = (estimate.execution_price * quantity).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)
        if side is Side.BUY:
            total_cost = position.average_cost * position.quantity + turnover + estimate.commission + estimate.tax
            position.quantity += quantity
            position.average_cost = (total_cost / position.quantity).quantize(Decimal("0.000001"))
            position.last_buy_date = trade_date
        else:
            position.quantity -= quantity
            position.sellable_quantity -= quantity
            if position.quantity == 0:
                position.average_cost = Decimal("0")
        self.trades.append(trade)
        return trade

    def make_bought_sellable(self, trade_date: date) -> None:
        for position in self.positions.values():
            if position.last_buy_date is not None and position.last_buy_date < trade_date:
                position.sellable_quantity = position.quantity

    def total_value(self, close_prices: dict[str, Decimal]) -> Decimal:
        value = self.cash
        for symbol, position in self.positions.items():
            if position.quantity:
                price = close_prices.get(symbol)
                if price is None or not price.is_finite() or price <= 0:
                    raise ValueError("持仓缺少有效估值价格")
                value += position.quantity * price
        return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)
