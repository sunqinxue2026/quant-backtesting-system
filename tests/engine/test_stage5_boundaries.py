"""确定性合成测试，不代表真实行情表现。"""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from quant_system.engine import BacktestEngine, CostModel, Portfolio, Side
from quant_system.strategies import DualMovingAverageStrategy
from quant_system.indicators import add_indicators


def bars():
    return pd.DataFrame(dict(symbol=['000001.SZ']*9,
        trade_date=pd.bdate_range('2024-01-02', periods=9),
        open=[10,9,8,9,10,11,10,9,8], close=[10,9,8,9,10,11,10,9,8], volume=[100]*9))


def free():
    return CostModel(commission_rate=0, minimum_commission=0, stamp_tax_rate=0, slippage_bps=0)


def test_raw_prices_indicators_signals_and_cash_match_manual():
    data=add_indicators(bars(), short_window=2, long_window=3)
    engine=BacktestEngine(DualMovingAverageStrategy(2,3), Decimal('10000'),free(),100)
    result=engine.run(data)
    assert [t.price for t in result.trades]==[Decimal('11'),Decimal('8')]
    assert result.orders[0].signal_date==data.iloc[4].trade_date
    assert result.trades[0].trade_date==data.iloc[5].trade_date
    assert result.snapshots[5].cash==Decimal('8900')
    assert result.snapshots[5].position_quantity==100
    assert result.final_cash==result.final_value==Decimal('9700')
    # 同一引擎再次调用不能继承前次持仓与现金。
    assert engine.run(data)==result


def test_auto_quantity_uses_execution_open_and_fees():
    data=add_indicators(bars(), short_window=2,long_window=3)
    result=BacktestEngine(DualMovingAverageStrategy(2,3),Decimal('10000'),free()).run(data)
    assert result.trades[0].quantity==900
    assert result.snapshots[5].cash==Decimal('100')
    assert result.final_cash==Decimal('7300')


def test_fees_slippage_sell_tax_exact_cash():
    p=Portfolio(Decimal('10000'),CostModel(commission_rate=Decimal('.001'),minimum_commission=5,stamp_tax_rate=Decimal('.001'),slippage_bps=100))
    buy=p.settle_trade('000001.SZ',Side.BUY,100,Decimal('10'),date(2024,1,2),1,1)
    assert (buy.price,buy.commission,buy.tax,p.cash)==(Decimal('10.1'),Decimal('5'),Decimal('0'),Decimal('8985'))
    p.make_bought_sellable(date(2024,1,3))
    sell=p.settle_trade('000001.SZ',Side.SELL,100,Decimal('11'),date(2024,1,3),2,2)
    assert sell.price==Decimal('10.89')
    assert sell.commission==Decimal('5')
    assert sell.tax==Decimal('1.09')
    assert p.cash==Decimal('10067.91')


@pytest.mark.parametrize('quantity',[0,-1,1.5,True,50])
def test_invalid_quantity_does_not_change_cash(quantity):
    p=Portfolio(Decimal('10000'))
    with pytest.raises(ValueError):
        p.settle_trade('000001.SZ',Side.BUY,quantity,Decimal('10'),date(2024,1,2),1,1)
    assert p.cash==Decimal('10000')
    assert not p.trades


@pytest.mark.parametrize('price',['0','-1','NaN','Infinity'])
def test_invalid_execution_price_rejects_order(price):
    data=add_indicators(bars(),short_window=2,long_window=3)
    data.loc[5,'open']=float(price)
    result=BacktestEngine(DualMovingAverageStrategy(2,3),Decimal('10000'),free(),100).run(data)
    assert result.orders[0].status.value=='REJECTED'
    assert not result.trades


def test_add_position_rejected_without_changing_cash():
    p=Portfolio(Decimal('10000'),free())
    p.settle_trade('000001.SZ',Side.BUY,100,Decimal('10'),date(2024,1,2),1,1)
    with pytest.raises(ValueError,match='加仓'):
        p.settle_trade('000001.SZ',Side.BUY,100,Decimal('10'),date(2024,1,3),2,2)
    assert p.cash==Decimal('9000')


@pytest.mark.parametrize('kind',['empty','duplicate','multiple','invalid_close'])
def test_bad_input_is_rejected(kind):
    data=add_indicators(bars(),short_window=2,long_window=3)
    if kind=='empty': data=data.iloc[:0]
    elif kind=='duplicate': data=pd.concat([data,data.iloc[:1]])
    elif kind=='multiple': data.loc[0,'symbol']='600000.SH'
    else: data.loc[0,'close']=float('inf')
    with pytest.raises(ValueError):
        BacktestEngine(DualMovingAverageStrategy(2,3),Decimal('10000')).run(data)


def test_duplicate_signals_rejected():
    class DuplicateStrategy:
        def generate_signals(self,data):
            return pd.DataFrame([dict(symbol='000001.SZ',trade_date=data.iloc[2].trade_date,side='BUY')]*2)
    with pytest.raises(ValueError,match='重复交易信号'):
        BacktestEngine(DuplicateStrategy(),Decimal('10000')).run(add_indicators(bars(),short_window=2,long_window=3))


def test_appending_future_prices_does_not_change_past_execution():
    data=bars()
    def run(frame):
        return BacktestEngine(DualMovingAverageStrategy(2,3),Decimal('10000'),free(),100).run(add_indicators(frame,short_window=2,long_window=3))
    prefix=run(data.iloc[:7])
    full=run(data)
    assert prefix.trades==full.trades[:len(prefix.trades)]
    assert prefix.snapshots==full.snapshots[:7]


def test_insufficient_cash_auto_and_zero_explicit_quantity():
    data=add_indicators(bars(),short_window=2,long_window=3)
    for cash,quantity in [(Decimal('1'),None),(Decimal('10000'),0)]:
        result=BacktestEngine(DualMovingAverageStrategy(2,3),cash,free(),quantity).run(data)
        assert not result.trades
        assert any(o.status.value=='REJECTED' for o in result.orders)
