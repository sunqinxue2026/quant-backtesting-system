from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN

from .models import Side, Trade
from .limits import MAX_ORDER_QUANTITY
from ..money import MONEY_QUANT, normalize_money, normalize_initial_cash


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
            if value < 0:
                raise ValueError("交易成本参数不能为负数")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "minimum_commission", normalize_money(self.minimum_commission))
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
        self.initial_cash = normalize_initial_cash(initial_cash)
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
        if (isinstance(quantity, bool) or not isinstance(quantity, int)
                or quantity <= 0 or quantity > MAX_ORDER_QUANTITY):
            raise ValueError("成交数量必须为1至MAX_ORDER_QUANTITY之间的整数")
        estimate = self.estimate(side, quantity, price)
        if side is Side.BUY and quantity % self.cost_model.lot_size:
            raise ValueError("买入数量不满足整手交易单位")
        position = self.positions.get(symbol)
        if side is Side.BUY and position is not None and position.quantity:
            raise ValueError("第一版不允许加仓")
        if side is Side.SELL and (position is None or position.sellable_quantity < quantity):
            raise ValueError("可卖数量不足或违反T+1")
        next_cash = normalize_money(self.cash + estimate.total_cash_change)
        if next_cash < 0:
            raise ValueError("资金不足，成交后现金不能为负数")
        # 所有可能失败的计算、对象构造和容器分配均在提交前完成。
        next_position = replace(position) if position is not None else Position(symbol=symbol)
        turnover = (estimate.execution_price * quantity).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)
        if side is Side.BUY:
            total_cost = next_position.average_cost * next_position.quantity + turnover + estimate.commission + estimate.tax
            next_position.quantity += quantity
            next_position.average_cost = (total_cost / next_position.quantity).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            next_position.last_buy_date = trade_date
        else:
            next_position.quantity -= quantity
            next_position.sellable_quantity -= quantity
            if next_position.quantity == 0:
                next_position.average_cost = Decimal("0")
        trade = Trade(trade_id, order_id, symbol, trade_date, side, quantity, estimate.execution_price, estimate.commission, estimate.tax, estimate.slippage)
        next_trades = [*self.trades, trade]
        next_positions = dict(self.positions)
        next_positions[symbol] = position if position is not None else next_position
        # 提交阶段不再执行 Decimal 运算、校验或外部调用。
        # 保留既有 Position 对象的引用；普通属性赋值不产生业务拒单。
        if position is not None:
            position.__dict__ = next_position.__dict__
        self.cash = next_cash
        self.positions = next_positions
        self.trades = next_trades
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
