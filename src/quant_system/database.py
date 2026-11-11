from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase):
    pass

class StockBasic(Base):
    __tablename__ = "stock_basic"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(64))
    list_date: Mapped[date | None] = mapped_column(Date)
    delist_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="listed")

class StockDaily(Base):
    __tablename__ = "stock_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(255))
    price_type: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("symbol", "trade_date", name="uq_stock_daily_symbol_date"),)

class StrategyConfig(Base):
    __tablename__ = "strategy_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    params_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class BacktestTask(Base):
    __tablename__ = "backtest_task"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    strategy_config_id: Mapped[int] = mapped_column(Integer)
    initial_capital: Mapped[float] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(16), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class BacktestSignal(Base):
    __tablename__ = "backtest_signal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    signal_date: Mapped[date] = mapped_column(Date)
    side: Mapped[str] = mapped_column(String(8))
    short_value: Mapped[float] = mapped_column(Float)
    long_value: Mapped[float] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("task_id", "signal_date", name="uq_signal_task_date"),)


class BacktestOrder(Base):
    __tablename__ = "backtest_order"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), index=True)
    signal_date: Mapped[date] = mapped_column(Date)
    execute_date: Mapped[date] = mapped_column(Date)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    order_id: Mapped[int] = mapped_column(Integer)
    trade_date: Mapped[date] = mapped_column(Date)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float)
    tax: Mapped[float] = mapped_column(Float)

class BacktestSnapshot(Base):
    __tablename__ = "backtest_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    cash: Mapped[float] = mapped_column(Numeric(18, 2))
    position_quantity: Mapped[int] = mapped_column(Integer)
    close_price: Mapped[float] = mapped_column(Numeric(18, 4))
    total_value: Mapped[float] = mapped_column(Numeric(18, 2))
    daily_return: Mapped[float] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("task_id", "trade_date", name="uq_snapshot_task_date"),)


class BacktestResult(Base):
    __tablename__ = "backtest_result"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("backtest_task.id"), unique=True)
    metrics_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def create_session_factory(url: str | None = None):
    database_url = url or os.getenv("DATABASE_URL", "sqlite:///quant_backtesting.db")
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
