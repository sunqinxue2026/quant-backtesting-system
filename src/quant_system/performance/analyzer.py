"""绩效公式v1；交易统计仅支持单股票、不加仓、完整退出。"""
from __future__ import annotations
import math
from decimal import Decimal, ROUND_HALF_EVEN
import numpy as np
import pandas as pd


def analyze_performance(snapshots, trades, initial_capital, *, annualization_days=252, risk_free_rate=0.0):
    """返回(metrics, curves)；首日收益以初始资金为分母，未定义值为None。"""
    if isinstance(annualization_days, bool) or not isinstance(annualization_days, int) or annualization_days <= 0:
        raise ValueError('年化交易日数必须为正整数')
    initial = float(initial_capital)
    if not math.isfinite(initial) or initial <= 0 or not math.isfinite(risk_free_rate) or risk_free_rate <= -1:
        raise ValueError('初始资金或无风险利率无效')
    frame = pd.DataFrame([{'trade_date': s.trade_date, 'equity': float(s.total_value), 'close': float(s.close_price)} for s in snapshots])
    if frame.empty:
        raise ValueError('账户快照不能为空')
    frame['trade_date'] = pd.to_datetime(frame.trade_date)
    frame = frame.sort_values('trade_date').reset_index(drop=True)
    if frame.trade_date.isna().any() or frame.trade_date.duplicated().any():
        raise ValueError('快照日期无效或重复')
    if not np.isfinite(frame[['equity','close']]).all().all() or (frame.equity < 0).any() or (frame.close <= 0).any():
        raise ValueError('资产或基准价格无效')
    equity = frame.equity.to_numpy()
    previous = np.r_[initial, equity[:-1]]
    if (previous == 0).any():
        raise ValueError('零资产之后的收益率未定义')
    returns = equity / previous - 1
    peak = np.maximum.accumulate(np.r_[initial, equity])[1:]
    frame['daily_return'] = returns
    frame['normalized_equity'] = equity / initial
    frame['drawdown'] = equity / peak - 1
    frame['benchmark_equity'] = frame.close / frame.close.iloc[0]
    span = (frame.trade_date.iloc[-1] - frame.trade_date.iloc[0]).days
    total = equity[-1] / initial - 1
    annual = None
    notes = []
    if span:
        try:
            annual = float((equity[-1] / initial) ** (365.25 / span) - 1)
            if not math.isfinite(annual):
                annual = None
                notes.append('年化收益数值溢出，返回null')
        except OverflowError:
            notes.append('年化收益数值溢出，返回null')
    else:
        notes.append('自然日跨度为0，年化收益为null')
    std = float(np.std(returns, ddof=1)) if len(returns) >= 2 else None
    daily_rf = math.expm1(math.log1p(risk_free_rate) / annualization_days)
    sharpe = None if std is None or std <= 1e-15 else float(np.mean(returns - daily_rf) / std * math.sqrt(annualization_days))
    if sharpe is None:
        notes.append('收益样本不足2个或标准差为0，夏普为null')
    dates = {d.date(): i for i,d in enumerate(frame.trade_date)}
    opened = None
    pnls, holdings = [], []
    money = lambda v: v.quantize(Decimal('.01'), rounding=ROUND_HALF_EVEN)
    for trade in sorted(trades, key=lambda t: (t.trade_date, t.id if hasattr(t, 'id') else t.trade_id)):
        side = getattr(trade.side, 'value', trade.side)
        if trade.trade_date not in dates or trade.quantity <= 0:
            raise ValueError('成交日期或数量无效')
        values = [Decimal(str(getattr(trade,k))) for k in ('price','commission','tax')]
        price, commission, tax = values
        if any(not v.is_finite() for v in values) or price <= 0 or commission < 0 or tax < 0:
            raise ValueError('成交金额无效')
        turnover = money(price * trade.quantity)
        if side == 'BUY' and opened is None:
            opened = (trade.quantity, turnover + commission + tax, dates[trade.trade_date])
        elif side == 'SELL' and opened is not None and trade.quantity == opened[0]:
            pnls.append(float(turnover - commission - tax - opened[1]))
            holdings.append(dates[trade.trade_date] - opened[2])
            opened = None
        else:
            raise ValueError('仅支持不加仓、完整平仓成交序列')
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    if not pnls:
        notes.append('无完整平仓，胜率、盈亏比、平均持仓时长为null')
    elif not wins or not losses:
        notes.append('缺少盈利或亏损样本，盈亏比为null')
    if span < 365:
        notes.append('短样本年化指标仅供公式核验，不用于评价策略有效性')
    metrics = dict(total_return=float(total), annualized_return=annual,
        annualized_volatility=None if std is None else std * math.sqrt(annualization_days),
        max_drawdown=float(frame.drawdown.min()), sharpe_ratio=sharpe,
        win_rate=len(wins)/len(pnls) if pnls else None,
        profit_loss_ratio=float(np.mean(wins)/np.mean(losses)) if wins and losses else None,
        trade_count=len(trades), closed_trade_count=len(pnls), open_trade_count=int(opened is not None),
        average_holding_days=float(np.mean(holdings)) if holdings else None,
        realized_net_pnl=sum(pnls), final_equity=float(equity[-1]),
        benchmark_total_return=float(frame.benchmark_equity.iloc[-1]-1), notes=notes,
        definitions=dict(version='1.0', annualization_days=annualization_days,
            annual_risk_free_rate=risk_free_rate, daily_risk_free_rate=daily_rf,
            risk_free_conversion='(1+annual_rf)^(1/annualization_days)-1',
            annual_return='(final/initial)^(365.25/calendar_days)-1',
            returns='首日equity/initial-1；之后equity/previous_equity-1；ddof=1',
            drawdown='包含初始资金的历史峰值；负值表示回撤',
            benchmark='同任务同批次同日期同价格口径收盘价/首日收盘价，无成本、无限分割买入持有；非可执行账户',
            trade_statistics='完整买入到退出；费用计入；持平计入胜率分母；未平仓不计胜率；持仓时长按行情交易日序号差'))
    return metrics, frame
