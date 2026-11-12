"""合成数据的手算公式、边界、数据库与PNG端到端验证。"""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
import json
import math
import struct

import pytest
from sqlalchemy import select

from quant_system.performance import analyze_performance, generate_report
from quant_system.engine import CostModel
from quant_system.engine.backtest import Snapshot
from quant_system.engine.models import Trade, Side
from quant_system.database import BacktestResult, BacktestSnapshot
from quant_system.backtest_pipeline import run_batch_backtest
import pandas as pd
from quant_system.database import create_session_factory
from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from quant_system.backtest_pipeline import BacktestRequest

def free():
    return CostModel(commission_rate=0, minimum_commission=0, stamp_tax_rate=0, slippage_bps=0)


def prices():
    values = [10, 9, 8, 9, 10, 11, 10, 9, 8]
    return pd.DataFrame(dict(symbol=['000001.SZ']*9,
        trade_date=pd.bdate_range('2024-01-02', periods=9).strftime('%Y-%m-%d'),
        open=values, high=[x+1 for x in values], low=[x-1 for x in values],
        close=values, volume=[100]*9, amount=[x*100 for x in values]))


def setup(tmp_path, frame=None):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'pipeline.db'}")
    path = tmp_path / 'synthetic.csv'
    (prices() if frame is None else frame).to_csv(path, index=False)
    imported = import_csv(DataLoadRequest(path, 'synthetic/test', '2024-01-12', '未复权',
        {'price': 'CNY', 'volume': '股', 'amount': 'CNY'}, True), factory)
    request = BacktestRequest(imported.batch_id, '000001.SZ', date(2024,1,2), date(2024,1,12), '未复权')
    return factory, imported, request




def snapshots(values, closes=None):
    return [Snapshot(date(2024,1,2)+timedelta(days=i),Decimal(str(v)),0,
        Decimal(str((closes or [10]*len(values))[i])),Decimal(str(v)),None)
        for i,v in enumerate(values)]


def test_manual_equity_return_drawdown_volatility_sharpe():
    metrics, curves=analyze_performance(snapshots([110,99,108]),[],100)
    assert metrics['total_return']==pytest.approx(.08)
    assert metrics['max_drawdown']==pytest.approx(-.1)
    expected=[.1,-.1,108/99-1]
    assert curves.daily_return.tolist()==pytest.approx(expected)
    mean=sum(expected)/3
    std=math.sqrt(sum((x-mean)**2 for x in expected)/2)
    assert metrics['annualized_volatility']==pytest.approx(std*math.sqrt(252))
    assert metrics['sharpe_ratio']==pytest.approx(mean/std*math.sqrt(252))
    assert metrics['annualized_return']==pytest.approx(1.08**(365.25/2)-1)


def test_initial_capital_included_in_peak_and_single_day():
    metrics, curves=analyze_performance(snapshots([90]),[],100)
    assert metrics['max_drawdown']==pytest.approx(-.1)
    assert metrics['annualized_return'] is None
    assert metrics['annualized_volatility'] is None
    assert metrics['sharpe_ratio'] is None
    assert metrics['win_rate'] is None


def test_zero_volatility_no_trades():
    metrics,_=analyze_performance(snapshots([100]*4),[],100)
    assert metrics['annualized_volatility']==0
    assert metrics['sharpe_ratio'] is None
    assert metrics['total_return']==metrics['max_drawdown']==0
    assert metrics['closed_trade_count']==metrics['trade_count']==0


def test_daily_risk_free_geometric_conversion():
    m,c=analyze_performance(snapshots([100,110,105]),[],100,risk_free_rate=.05,annualization_days=250)
    rf=1.05**(1/250)-1
    assert m['definitions']['daily_risk_free_rate']==pytest.approx(rf)
    mean=sum(c.daily_return)/3
    std=math.sqrt(sum((x-mean)**2 for x in c.daily_return)/2)
    assert m['sharpe_ratio']==pytest.approx((mean-rf)/std*math.sqrt(250))


def trade(i,day,side,price,commission=0,tax=0):
    return Trade(i,i,'000001.SZ',date(2024,1,2)+timedelta(days=day),Side(side),100,
        Decimal(str(price)),Decimal(str(commission)),Decimal(str(tax)),Decimal('0'))


def test_round_trip_fees_win_loss_holding_and_open_trade():
    trades=[trade(1,0,'BUY',10,5),trade(2,1,'SELL',11,5,1.1),
        trade(3,2,'BUY',10,5),trade(4,4,'SELL',9,5,.9),trade(5,5,'BUY',8,5)]
    m,_=analyze_performance(snapshots([10000]*6),trades,10000)
    assert m['trade_count']==5 and m['closed_trade_count']==2 and m['open_trade_count']==1
    assert m['win_rate']==.5
    assert m['profit_loss_ratio']==pytest.approx(88.9/110.9)
    assert m['average_holding_days']==1.5
    assert m['realized_net_pnl']==pytest.approx(-22)


def test_break_even_trade_in_win_rate_denominator():
    m,_=analyze_performance(snapshots([100,100]),[trade(1,0,'BUY',10),trade(2,1,'SELL',10)],100)
    assert m['win_rate']==0 and m['profit_loss_ratio'] is None


def test_zero_terminal_equity():
    m,_=analyze_performance(snapshots([100,0]),[],100)
    assert m['total_return']==m['annualized_return']==m['max_drawdown']==-1


@pytest.mark.parametrize('kwargs',[
    {'annualization_days':0},{'annualization_days':True},
    {'risk_free_rate':-1},{'risk_free_rate':float('nan')}])
def test_invalid_analysis_configuration(kwargs):
    with pytest.raises(ValueError):
        analyze_performance(snapshots([100]),[],100,**kwargs)


@pytest.mark.parametrize('values',[[],[-1],[float('inf')],[0,1]])
def test_invalid_equity(values):
    with pytest.raises(ValueError):
        analyze_performance(snapshots(values),[],100)


def test_duplicate_snapshot_dates():
    data=snapshots([100,100]);data[1]=data[0]
    with pytest.raises(ValueError):
        analyze_performance(data,[],100)


def test_invalid_trade_sequence_rejected():
    with pytest.raises(ValueError,match='成交序列'):
        analyze_performance(snapshots([100,100]),[trade(1,0,'SELL',10)],100)


def test_csv_to_execution_to_performance_database_and_four_pngs(tmp_path):
    factory, imported, request=setup(tmp_path)
    execution=run_batch_backtest(request,factory,free())
    report=generate_report(factory,execution.task_id,tmp_path/'report')
    m=report['metrics']
    assert m['total_return']==pytest.approx(-.03)
    assert m['max_drawdown']==pytest.approx(-.03)
    assert m['benchmark_total_return']==pytest.approx(-.2)
    assert m['closed_trade_count']==1 and m['trade_count']==2
    assert m['average_holding_days']==3
    assert m['realized_net_pnl']==-300
    assert m['final_equity']==9700
    assert report['metadata']['is_synthetic'] is True
    folder=tmp_path/'report'/f'task_{execution.task_id}'
    assert json.loads((folder/'report.json').read_text(encoding='utf-8'))==report
    for name in report['files'][:4]:
        data=(folder/name).read_bytes()
        assert data[:8]==b'\x89PNG\r\n\x1a\n'
        width,height=struct.unpack('>II',data[16:24])
        assert width>=1000 and height>=600 and len(data)>10000
    with factory() as session:
        saved=session.scalar(select(BacktestResult).where(BacktestResult.task_id==execution.task_id))
        assert saved.metrics_json==report
    with pytest.raises(ValueError,match='已保存'):
        generate_report(factory,execution.task_id,tmp_path/'report')
    factory.kw['bind'].dispose()


def test_report_rejects_misaligned_snapshot_dates(tmp_path):
    factory,_,request=setup(tmp_path)
    execution=run_batch_backtest(request,factory,free())
    with factory.begin() as session:
        row=session.scalar(select(BacktestSnapshot).where(BacktestSnapshot.task_id==execution.task_id))
        row.trade_date=date(2023,12,1)
    with pytest.raises(ValueError):
        generate_report(factory,execution.task_id,tmp_path/'report')
    with factory() as session:
        assert session.scalar(select(BacktestResult.id)) is None


def test_file_failure_does_not_save_metrics(tmp_path,monkeypatch):
    import quant_system.performance.report as module
    factory,_,request=setup(tmp_path)
    execution=run_batch_backtest(request,factory,free())
    def fail(*args):
        raise OSError('synthetic failure')
    monkeypatch.setattr(module,'plot_report',fail)
    with pytest.raises(OSError):
        generate_report(factory,execution.task_id,tmp_path/'report')
    with factory() as session:
        assert session.scalar(select(BacktestResult.id)) is None


def test_cost_configuration_and_saved_equity_used(tmp_path):
    factory,_,request=setup(tmp_path)
    result=run_batch_backtest(request,factory,CostModel(commission_rate='.001',minimum_commission=5,stamp_tax_rate='.001',slippage_bps=100))
    report=generate_report(factory,result.task_id,tmp_path/'report')
    assert report['metrics']['final_equity']==9670.21
    assert report['metrics']['realized_net_pnl']==pytest.approx(-329.79)
    assert report['metadata']['parameters']['costs']['slippage_bps']=='100'
