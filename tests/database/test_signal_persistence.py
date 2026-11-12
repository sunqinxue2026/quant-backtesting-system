from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from quant_system.database import BacktestSignal, BacktestTask, DataImportBatch, StrategyConfig, create_session_factory
from quant_system.repository import MarketDataRepository


def create_task(factory):
    with factory.begin() as session:
        batch = DataImportBatch(
            source="synthetic/test",
            source_file="signals.csv",
            data_as_of=date(2024, 1, 5),
            price_type="未复权",
            units_json={},
            is_synthetic=True,
            input_rows=5,
            accepted_rows=5,
            quality_status="accepted",
        )
        config = StrategyConfig(name="dual_ma", params_json={"short_window": 2, "long_window": 3})
        session.add_all([batch, config])
        session.flush()
        task = BacktestTask(
            symbol="000001.SZ",
            strategy_config_id=config.id,
            data_batch_id=batch.id,
            initial_capital=Decimal("100000.00"),
        )
        session.add(task)
        session.flush()
        return task.id


def signal(task_id: int, signal_date: date = date(2024, 1, 3), side: str = "BUY") -> BacktestSignal:
    return BacktestSignal(
        task_id=task_id,
        symbol="000001.SZ",
        signal_date=signal_date,
        side=side,
        short_value=Decimal("11.00000000"),
        long_value=Decimal("10.00000000"),
    )


def test_signal_can_be_saved_and_queried_by_task(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'signals.db'}")
    task_id = create_task(factory)
    with factory.begin() as session:
        assert MarketDataRepository(session).add_signal_batch([signal(task_id)]) == 1
    with factory() as session:
        rows = MarketDataRepository(session).query_signals(task_id)
        assert len(rows) == 1
        assert rows[0].side == "BUY"
        assert rows[0].signal_date == date(2024, 1, 3)


def test_duplicate_signal_is_rejected_and_transaction_rolls_back(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'duplicate-signals.db'}")
    task_id = create_task(factory)
    with factory.begin() as session:
        MarketDataRepository(session).add_signal_batch([signal(task_id)])
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            MarketDataRepository(session).add_signal_batch([signal(task_id), signal(task_id, date(2024, 1, 4), "SELL")])
    with factory() as session:
        rows = MarketDataRepository(session).query_signals(task_id)
        assert len(rows) == 1
        assert rows[0].signal_date == date(2024, 1, 3)
