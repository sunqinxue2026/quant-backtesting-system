from decimal import Decimal

import pytest
from sqlalchemy import select

from quant_system.database import create_session_factory, StrategyConfig, BacktestTask, BacktestOrder, BacktestTrade
from quant_system.engine import BacktestEngine
from quant_system.engine.persistence import save_execution, query_execution
from quant_system.strategies import DualMovingAverageStrategy
from quant_system.indicators import add_indicators
from .test_stage5_boundaries import bars, free


def task(factory):
    with factory.begin() as session:
        config=StrategyConfig(name='synthetic/test', params_json={'short_window':2,'long_window':3})
        session.add(config)
        session.flush()
        row=BacktestTask(symbol='000001.SZ',strategy_config_id=config.id,initial_capital=Decimal('10000'))
        session.add(row)
        session.flush()
        return row.id


def execution():
    return BacktestEngine(DualMovingAverageStrategy(2,3),Decimal('10000'),free(),100).run(add_indicators(bars(),short_window=2,long_window=3))


def test_save_query_and_duplicate_protection(tmp_path):
    factory=create_session_factory(f"sqlite:///{tmp_path / 'execution.db'}")
    task_id=task(factory)
    with factory.begin() as session:
        save_execution(session,task_id,execution())
    with factory() as session:
        rows=query_execution(session,task_id)
        assert [len(rows[k]) for k in ('orders','trades','snapshots')]==[2,2,9]
        assert rows['trades'][0].order_id==rows['orders'][0].id
        assert rows['snapshots'][-1].cash==Decimal('9700')
        assert session.get(BacktestTask,task_id).status=='completed'
    with pytest.raises(ValueError,match='已经保存'):
        with factory.begin() as session:
            save_execution(session,task_id,execution())
    with factory() as session:
        assert len(query_execution(session,task_id)['trades'])==2


def test_caller_exception_rolls_back_everything(tmp_path):
    factory=create_session_factory(f"sqlite:///{tmp_path / 'rollback.db'}")
    task_id=task(factory)
    with pytest.raises(RuntimeError):
        with factory.begin() as session:
            save_execution(session,task_id,execution())
            raise RuntimeError('synthetic forced failure')
    with factory() as session:
        assert all(not rows for rows in query_execution(session,task_id).values())
        assert session.get(BacktestTask,task_id).status=='created'


def test_missing_task_rejected(tmp_path):
    factory=create_session_factory(f"sqlite:///{tmp_path / 'missing.db'}")
    with pytest.raises(ValueError,match='任务不存在'):
        with factory.begin() as session:
            save_execution(session,999,execution())


@pytest.mark.parametrize('completed', [False, True])
def test_invalid_execution_rejected_before_writes(tmp_path, completed):
    from dataclasses import replace
    factory = create_session_factory(f"sqlite:///{tmp_path / 'invalid.db'}")
    task_id = task(factory)
    if completed:
        with factory.begin() as session:
            session.get(BacktestTask, task_id).status = 'completed'
    result = execution() if completed else replace(execution(), snapshots=[])
    message = '已经保存' if completed else '快照不能为空'
    with pytest.raises(ValueError, match=message):
        with factory.begin() as session:
            save_execution(session, task_id, result)
    with factory() as session:
        assert all(not rows for rows in query_execution(session, task_id).values())
        assert session.get(BacktestTask, task_id).status == ('completed' if completed else 'created')
    factory.kw['bind'].dispose()
