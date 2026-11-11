from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class StockBasic(Base):
    __tablename__ = "stock_basic"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(8), nullable=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delist_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="listed", nullable=False)


class DataImportBatch(Base):
    __tablename__ = "data_import_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_type: Mapped[str] = mapped_column(String(32), nullable=False)
    units_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(default=False, nullable=False)
    input_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), default="raw", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StockDaily(Base):
    __tablename__ = "stock_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", "price_type", name="uq_stock_daily_symbol_date_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    price_type: Mapped[str] = mapped_column(String(32), nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("data_import_batch.id"), nullable=True, index=True)


class StrategyConfig(Base):
    __tablename__ = "strategy_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class BacktestTask(Base):
    __tablename__ = "backtest_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    strategy_config_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategy_config.id"), nullable=False)
    data_batch_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("data_import_batch.id"), nullable=True)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="created", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class BacktestSignal(Base):
    __tablename__ = "backtest_signal"
    __table_args__ = (UniqueConstraint("task_id", "signal_date", name="uq_signal_task_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    short_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    long_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)


class BacktestOrder(Base):
    __tablename__ = "backtest_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), nullable=False, index=True)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    execute_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_order.id"), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)


class BacktestSnapshot(Base):
    __tablename__ = "backtest_snapshot"
    __table_args__ = (UniqueConstraint("task_id", "trade_date", name="uq_snapshot_task_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    position_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 10), nullable=True)


class BacktestResult(Base):
    __tablename__ = "backtest_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), nullable=False, unique=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


def create_engine_from_config(url: str | None = None) -> Engine:
    database_url = url or os.getenv("DATABASE_URL", "sqlite:///quant_backtesting.db")
    return create_engine(database_url, future=True)


def create_session_factory(url: str | None = None) -> sessionmaker[Session]:
    engine = create_engine_from_config(url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
