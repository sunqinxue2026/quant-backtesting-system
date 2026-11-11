from __future__ import annotations

import json
from datetime import date

import pandas as pd
from sqlalchemy import select

from quant_system.database import BacktestResult, BacktestSnapshot, create_session_factory
from quant_system.engine.models import Trade
from quant_system.performance.analyzer import PerformanceAnalyzer
from quant_system.repository import QuantRepository


def test_performance_pairs_completed_trades() -> None:
    trades = [
        Trade(date(2024, 1, 2), "BUY", 100, 10.0, 1.0, 0.0),
        Trade(date(2024, 1, 5), "SELL", 100, 11.0, 1.0, 0.5),
        Trade(date(2024, 1, 8), "BUY", 100, 10.0, 1.0, 0.0),
    ]
    snapshots = pd.DataFrame({"total_value": [1000, 1050, 1100], "daily_return": [0.0, 0.05, 0.0476]})
    metrics = PerformanceAnalyzer(risk_free_rate=0).analyze(snapshots, trades)
    assert metrics["completed_trade_count"] == 1
    assert metrics["win_rate"] == 1
    # 没有亏损交易时没有盈亏比的分母，按需求口径返回空值。
    assert metrics["profit_loss_ratio"] is None
    assert metrics["average_holding_days"] == 3

    mixed_trades = trades + [
        Trade(date(2024, 1, 9), "SELL", 100, 9.0, 1.0, 0.5),
    ]
    mixed_metrics = PerformanceAnalyzer(risk_free_rate=0).analyze(snapshots, mixed_trades)
    assert mixed_metrics["completed_trade_count"] == 2
    assert mixed_metrics["win_rate"] == 0.5
    assert mixed_metrics["profit_loss_ratio"] > 0


def test_repository_writes_snapshot_and_result_transactionally() -> None:
    session_factory = create_session_factory("sqlite+pysqlite:///:memory:")
    with session_factory() as session:
        repo = QuantRepository(session)
        config = repo.add_strategy_config("dual_ma", {"short": 2, "long": 3})
        task = repo.add_task("000001.SZ", config.id, 10000)
        snapshots = pd.DataFrame({
            "trade_date": ["2024-01-02"], "cash": [10000], "position_quantity": [0],
            "close_price": [10], "total_value": [10000], "daily_return": [0],
        })
        repo.save_backtest(task.id, pd.DataFrame(columns=["symbol", "trade_date", "side", "sma_short", "sma_long"]), [], [], snapshots, {"total_return": 0.0})
        repo.commit()
        assert session.scalar(select(BacktestSnapshot).where(BacktestSnapshot.task_id == task.id)) is not None
        result = session.scalar(select(BacktestResult).where(BacktestResult.task_id == task.id))
        assert json.loads(result.metrics_json)["total_return"] == 0.0
