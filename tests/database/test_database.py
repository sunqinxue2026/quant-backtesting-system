from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from quant_system.database import (
    BacktestTask,
    Base,
    DataImportBatch,
    StockDaily,
    StrategyConfig,
    create_engine_from_config,
    create_session_factory,
)
from quant_system.repository import MarketDataRepository


def daily(symbol: str = "000001.SZ", trade_date: date = date(2024, 1, 2)) -> StockDaily:
    return StockDaily(
        symbol=symbol,
        trade_date=trade_date,
        open=Decimal("10.000000"),
        high=Decimal("10.500000"),
        low=Decimal("9.800000"),
        close=Decimal("10.200000"),
        volume=Decimal("1000"),
        amount=Decimal("10200"),
        source="synthetic/test",
        price_type="前复权研究口径",
    )


def test_sqlite_creates_all_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine_from_config(url)
    Base.metadata.create_all(engine)
    table_names = set(inspect(engine).get_table_names())
    assert {
        "stock_basic", "data_import_batch", "stock_daily", "strategy_config",
        "backtest_task", "backtest_signal", "backtest_order", "backtest_trade",
        "backtest_snapshot", "backtest_result",
    } <= table_names


def test_batch_insert_and_date_query_are_ordered(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'query.db'}")
    with factory.begin() as session:
        repo = MarketDataRepository(session)
        repo.bulk_insert_daily([
            daily(trade_date=date(2024, 1, 3)),
            daily(trade_date=date(2024, 1, 2)),
        ])
    with factory() as session:
        rows = MarketDataRepository(session).query_daily(
            "000001.SZ", date(2024, 1, 1), date(2024, 1, 31), "前复权研究口径"
        )
        assert [row.trade_date for row in rows] == [date(2024, 1, 2), date(2024, 1, 3)]
        assert rows[0].close == Decimal("10.200000")


def test_duplicate_daily_row_rolls_back_transaction(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'rollback.db'}")
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            repo = MarketDataRepository(session)
            repo.bulk_insert_daily([daily(), daily()])
    with factory() as session:
        assert MarketDataRepository(session).count_daily() == 0


def test_import_batch_and_task_are_persisted_together(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'relation.db'}")
    with factory.begin() as session:
        batch = DataImportBatch(
            source="synthetic/test",
            source_file="demo.csv",
            data_as_of=date(2024, 1, 3),
            price_type="前复权研究口径",
            units_json={"price": "CNY", "volume": "股", "amount": "CNY"},
            is_synthetic=True,
            input_rows=2,
            accepted_rows=2,
            quality_status="accepted",
        )
        strategy = StrategyConfig(name="placeholder-for-stage-3", params_json={"note": "no strategy logic"})
        session.add_all([batch, strategy])
        session.flush()
        task = BacktestTask(
            symbol="000001.SZ",
            strategy_config_id=strategy.id,
            data_batch_id=batch.id,
            initial_capital=Decimal("100000.00"),
        )
        session.add(task)
        session.flush()
        assert task.id is not None
        assert batch.id is not None
        assert strategy.id is not None
