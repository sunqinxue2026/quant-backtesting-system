from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import BacktestSignal, BacktestSnapshot, DataImportBatch, StockDaily


class MarketDataRepository:
    """行情和导入批次的数据访问层；事务边界由调用方控制。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_import_batch(self, batch: DataImportBatch) -> DataImportBatch:
        self.session.add(batch)
        self.session.flush()
        return batch

    def bulk_insert_daily(self, rows: Iterable[StockDaily]) -> int:
        items = list(rows)
        if items:
            self.session.add_all(items)
            self.session.flush()
        return len(items)

    def query_daily(self, symbol: str, start: date, end: date, price_type: str) -> list[StockDaily]:
        statement = (
            select(StockDaily)
            .where(
                StockDaily.symbol == symbol,
                StockDaily.trade_date >= start,
                StockDaily.trade_date <= end,
                StockDaily.price_type == price_type,
            )
            .order_by(StockDaily.trade_date)
        )
        return list(self.session.scalars(statement))

    def count_daily(self, symbol: str | None = None) -> int:
        statement = select(StockDaily)
        if symbol is not None:
            statement = statement.where(StockDaily.symbol == symbol)
        return len(list(self.session.scalars(statement)))

    def add_snapshot_batch(self, snapshots: Iterable[BacktestSnapshot]) -> int:
        items = list(snapshots)
        if items:
            self.session.add_all(items)
            self.session.flush()
        return len(items)

    def add_signal_batch(self, signals: Iterable[BacktestSignal]) -> int:
        items = list(signals)
        if items:
            self.session.add_all(items)
            self.session.flush()
        return len(items)

    def query_signals(self, task_id: int) -> list[BacktestSignal]:
        statement = (
            select(BacktestSignal)
            .where(BacktestSignal.task_id == task_id)
            .order_by(BacktestSignal.signal_date)
        )
        return list(self.session.scalars(statement))
