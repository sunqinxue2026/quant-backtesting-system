"""资金金额统一为分；比例参数和成交价格不使用此规范化。"""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

MONEY_QUANT = Decimal("0.01")


def normalize_money(value: Decimal) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("资金金额必须是有限数值")
    # 分位系数需要整数位 + 两位小数，并为舍入进位预留一位。
    # 不修改调用方上下文，不依赖其 prec 或 rounding。
    with localcontext() as context:
        context.prec = max(1, amount.adjusted() + 4)
        return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)


def normalize_initial_cash(value: Decimal) -> Decimal:
    amount = normalize_money(value)
    if amount <= 0:
        raise ValueError("初始资金按分规范化后必须大于零")
    return amount
