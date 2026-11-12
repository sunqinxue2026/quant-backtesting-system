"""使用真实模块的synthetic/test全链路测试，不连接真实MySQL。"""
from datetime import date
from decimal import Decimal
from dataclasses import replace

import pandas as pd
import pytest
from sqlalchemy import select, func

from quant_system.database import (create_session_factory, DataImportBatch, StockDaily,
    BacktestTask, StrategyConfig, BacktestSignal, BacktestOrder, BacktestTrade, BacktestSnapshot)
from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from quant_system.backtest_pipeline import BacktestRequest, load_batch_frame, run_batch_backtest
from quant_system.engine import CostModel, BacktestEngine
from quant_system.engine.persistence import query_execution, save_execution
from quant_system.indicators import add_indicators
from quant_system.strategies import DualMovingAverageStrategy


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


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_csv_to_database_to_execution_matches_every_snapshot(tmp_path):
    factory, imported, request = setup(tmp_path)
    assert imported.inserted_rows == 9
    result = run_batch_backtest(request, factory, free())
    assert result.signals.side.tolist() == ['BUY', 'SELL']
    assert result.signals.trade_date.tolist() == [date(2024,1,8), date(2024,1,11)]
    assert [x.trade_date for x in result.execution.trades] == [date(2024,1,9), date(2024,1,12)]
    assert [x.price for x in result.execution.trades] == [Decimal('11'), Decimal('8')]
    with factory() as session:
        frame = load_batch_frame(session, request)
        for column in prices().columns[2:]:
            assert frame[column].tolist() == prices()[column].tolist()
        saved = query_execution(session, result.task_id)
        assert [len(saved[k]) for k in ('orders','trades','snapshots')] == [2,2,9]
        assert [x.cash for x in saved['snapshots']] == list(map(Decimal, ['10000']*5+['8900']*3+['9700']))
        assert [x.total_value for x in saved['snapshots']] == list(map(Decimal, ['10000']*6+['9900','9800','9700']))
        assert [x.position_quantity for x in saved['snapshots']] == [0]*5+[100]*3+[0]
        assert len(session.scalars(select(BacktestSignal)).all()) == 2
        task = session.get(BacktestTask, result.task_id)
        assert task.data_batch_id == imported.batch_id and task.status == 'completed'
        config = session.get(StrategyConfig, task.strategy_config_id)
        assert config.params_json['costs']['stamp_tax_rate'] == '0'
    with pytest.raises(ValueError, match='已经保存'):
        with factory.begin() as session:
            save_execution(session, result.task_id, result.execution)
    with factory() as session:
        assert count(session, BacktestTrade) == 2


def test_quality_categories_and_batch_isolation(tmp_path):
    original = prices()
    bad = original.iloc[[0]].assign(symbol='000002.SZ', high=1)
    review = original.iloc[[0]].assign(symbol='000003.SZ', volume=0, amount=0)
    factory, imported, request = setup(tmp_path, pd.concat([original, original.iloc[[0]], bad, review]))
    assert (imported.cleaning.report.accepted_rows, imported.cleaning.report.review_rows,
        imported.cleaning.report.rejected_rows, imported.cleaning.report.duplicate_removed_rows) == (9,1,1,1)
    # 同股票同口径但不同日期、不同批次的行情，不应混入本次回测。
    with factory.begin() as session:
        batch = DataImportBatch(source='synthetic/test',source_file='other',price_type='未复权',units_json={},accepted_rows=1)
        session.add(batch); session.flush()
        session.add(StockDaily(symbol='000001.SZ',trade_date=date(2024,1,15),open=99,high=100,low=98,
            close=99,volume=1,amount=99,source='synthetic/test',price_type='未复权',import_batch_id=batch.id))
    result = run_batch_backtest(replace(request, end=date(2024,1,15)), factory, free())
    assert len(result.execution.snapshots) == 9
    assert result.execution.final_value == Decimal('9700')
    with pytest.raises(ValueError, match='价格口径'):
        run_batch_backtest(replace(request, price_type='后复权'), factory, free())


@pytest.mark.parametrize('kind', ['empty_batch','empty_range','units','dates'])
def test_invalid_request_creates_no_task(tmp_path, kind):
    factory, _, request = setup(tmp_path)
    if kind in ('empty_batch','units'):
        with factory.begin() as session:
            batch = session.get(DataImportBatch, request.batch_id)
            if kind == 'empty_batch': batch.accepted_rows = 0
            else: batch.units_json = {'volume':'手'}
    elif kind == 'empty_range': request = replace(request, start=date(2025,1,1),end=date(2025,1,2))
    else: request = replace(request, start=date(2025,1,1))
    with pytest.raises(ValueError): run_batch_backtest(request, factory, free())
    with factory() as session:
        assert count(session, BacktestTask) == count(session, StrategyConfig) == 0


def test_execution_failure_rolls_back_new_task_but_keeps_import(tmp_path, monkeypatch):
    import quant_system.backtest_pipeline as pipeline
    factory, _, request = setup(tmp_path)
    actual = pipeline.save_execution
    def fail(session, task_id, result):
        actual(session, task_id, result)
        raise RuntimeError('synthetic forced failure after flush')
    monkeypatch.setattr(pipeline, 'save_execution', fail)
    with pytest.raises(RuntimeError): run_batch_backtest(request, factory, free())
    with factory() as session:
        for model in (StrategyConfig, BacktestTask, BacktestSignal, BacktestOrder, BacktestTrade, BacktestSnapshot):
            assert count(session, model) == 0
        assert count(session, DataImportBatch) == 1
        assert count(session, StockDaily) == 9


def test_cost_configuration_reaches_execution_and_storage(tmp_path):
    factory, _, request = setup(tmp_path)
    costs = CostModel(commission_rate=Decimal('.001'), minimum_commission=5,
                      stamp_tax_rate=Decimal('.001'), slippage_bps=100)
    result = run_batch_backtest(request, factory, costs)
    # 买价11.11，支出1111+5；卖价7.92，收入792-5-0.79。
    assert result.execution.final_value == Decimal('9670.21')
    with factory() as session:
        rows = query_execution(session,result.task_id)
        assert [x.price for x in rows['trades']] == [Decimal('11.11'),Decimal('7.92')]
        assert rows['snapshots'][-1].cash == Decimal('9670.21')


def test_future_data_does_not_change_past_pipeline_execution(tmp_path):
    factory, _, request = setup(tmp_path)
    prefix = run_batch_backtest(replace(request,end=date(2024,1,10)),factory,free())
    full = run_batch_backtest(request,factory,free())
    assert prefix.execution.snapshots == full.execution.snapshots[:7]
    assert prefix.execution.trades == full.execution.trades[:1]


def test_mismatched_indicator_parameters_are_rejected():
    data = add_indicators(prices(),short_window=2,long_window=3)
    with pytest.raises(ValueError,match='参数不一致'):
        BacktestEngine(DualMovingAverageStrategy(5,20),Decimal('10000')).run(data)


@pytest.mark.parametrize('kind',['side','symbol','date','missing'])
def test_invalid_signal_contract_is_rejected(kind):
    class InvalidStrategy:
        def generate_signals(self, data):
            row = dict(symbol='000001.SZ',trade_date=data.iloc[0].trade_date,side='BUY')
            if kind == 'side': row['side']='HOLD'
            elif kind == 'symbol': row['symbol']='600000.SH'
            elif kind == 'date': row['trade_date']='2030-01-01'
            else: del row['side']
            return pd.DataFrame([row])
    with pytest.raises(ValueError,match='信号'):
        BacktestEngine(InvalidStrategy(),Decimal('10000')).run(prices())
