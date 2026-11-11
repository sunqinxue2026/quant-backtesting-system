from __future__ import annotations

from datetime import date
import json

import pandas as pd

from quant_system.cleaning.cleaner import MarketDataCleaner
from quant_system.data.loader import MarketData
from quant_system.engine.backtest import BacktestEngine
from quant_system.engine.portfolio import Portfolio
from quant_system.engine.models import Trade
from quant_system.performance.analyzer import PerformanceAnalyzer


def test_cleaner_keeps_source_metadata_and_rejects_conflicting_duplicate() -> None:
    frame = pd.DataFrame([
        {"symbol": "000001.sz", "trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "amount": 1000},
        {"symbol": "000001.SZ", "trade_date": "2024-01-02", "open": 10, "high": 12, "low": 9, "close": 10, "volume": 100, "amount": 1000},
    ])
    cleaned, report = MarketDataCleaner().clean(MarketData(frame, "real.csv", "unadjusted", metadata={"data_as_of": "2024-01-02"}))
    assert cleaned.empty
    assert report.conflicting_duplicate_rows == 1
    assert report.price_type == "unadjusted"
    assert report.data_as_of == "2024-01-02"


def test_t_plus_one_and_minimum_commission() -> None:
    portfolio = Portfolio(10000, commission_rate=0.0001, min_commission=5, stamp_tax_rate=0, slippage_bps=0, lot_size=100)
    buy = portfolio.execute("BUY", 100, 10, date(2024, 1, 2))
    assert buy is not None and buy.commission == 5
    assert portfolio.execute("SELL", 100, 11, date(2024, 1, 2)) is None
    sell = portfolio.execute("SELL", 100, 11, date(2024, 1, 3))
    assert sell is not None and sell.commission == 5


def test_last_signal_expires_without_next_day() -> None:
    data = pd.DataFrame({"trade_date": ["2024-01-02"], "open": [10], "close": [10]})
    signals = pd.DataFrame({"trade_date": ["2024-01-02"], "side": ["BUY"]})
    result = BacktestEngine(Portfolio(10000)).run(data, signals)
    assert result.orders[-1].status == "EXPIRED"
    assert result.orders[-1].reason == "no_next_trading_day"


def test_performance_returns_empty_boundary_metrics() -> None:
    snapshots = pd.DataFrame({"trade_date": ["2024-01-02"], "total_value": [1000], "daily_return": [0.0]})
    metrics = PerformanceAnalyzer(risk_free_rate=0).analyze(snapshots, [])
    assert metrics["annualized_return"] is None
    assert metrics["annualized_volatility"] is None
    assert metrics["sharpe_ratio"] is None
    assert metrics["win_rate"] is None


def test_trade_net_cash_flow() -> None:
    trade = Trade(date(2024, 1, 2), "BUY", 100, 10, 1, 0)
    assert trade.net_cash_flow == -1001
