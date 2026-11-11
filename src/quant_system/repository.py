from __future__ import annotations

import json
from datetime import date
from typing import Iterable

import pandas as pd
from sqlalchemy.orm import Session

from quant_system.database import (
    BacktestOrder,
    BacktestResult,
    BacktestSignal,
    BacktestSnapshot,
    BacktestTask,
    BacktestTrade,
    StockDaily,
    StrategyConfig,
)
from quant_system.engine.models import Order, Trade


class QuantRepository:
    """量化业务数据访问层：单个业务操作使用一个事务。"""

    def __init__(self, session: Session):
        self.session = session

    def add_strategy_config(self, name: str, params: dict) -> StrategyConfig:
        row = StrategyConfig(name=name, params_json=json.dumps(params, ensure_ascii=False))
        self.session.add(row)
        self.session.flush()
        return row

    def add_task(self, symbol: str, strategy_config_id: int, initial_capital: float) -> BacktestTask:
        row = BacktestTask(symbol=symbol, strategy_config_id=strategy_config_id, initial_capital=initial_capital)
        self.session.add(row)
        self.session.flush()
        return row

    def bulk_insert_daily(self, frame: pd.DataFrame, source: str, price_type: str) -> int:
        records = frame.to_dict("records")
        self.session.bulk_insert_mappings(
            StockDaily,
            [{**record, "source": source, "price_type": price_type} for record in records],
        )
        return len(records)

    def save_backtest(
        self,
        task_id: int,
        signals: pd.DataFrame,
        orders: Iterable[Order],
        trades: Iterable[Trade],
        snapshots: pd.DataFrame,
        metrics: dict[str, float],
    ) -> None:
        for row in signals.to_dict("records"):
            self.session.add(BacktestSignal(
                task_id=task_id,
                symbol=str(row["symbol"]),
                signal_date=pd.Timestamp(row["trade_date"]).date(),
                side=str(row["side"]),
                short_value=float(row["sma_short"]),
                long_value=float(row["sma_long"]),
            ))
        self.session.bulk_save_objects([
            BacktestOrder(
                task_id=task_id,
                signal_date=order.signal_date,
                execute_date=order.execute_date,
                side=order.side,
                quantity=order.quantity,
                status=order.status,
            ) for order in orders
        ])
        self.session.bulk_save_objects([
            BacktestTrade(
                task_id=task_id,
                trade_date=trade.trade_date,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                commission=trade.commission,
                tax=trade.tax,
            ) for trade in trades
        ])
        self.session.bulk_save_objects([
            BacktestSnapshot(
                task_id=task_id,
                trade_date=pd.Timestamp(row["trade_date"]).date(),
                cash=float(row["cash"]),
                position_quantity=int(row["position_quantity"]),
                close_price=float(row["close_price"]),
                total_value=float(row["total_value"]),
                daily_return=float(row["daily_return"]),
            ) for row in snapshots.to_dict("records")
        ])
        self.session.add(BacktestResult(task_id=task_id, metrics_json=json.dumps(metrics, ensure_ascii=False)))

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
