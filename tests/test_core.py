from __future__ import annotations

import math
import pandas as pd
import pytest

from quant_system.cleaning.cleaner import MarketDataCleaner
from quant_system.data.loader import MarketData
from quant_system.engine.backtest import BacktestEngine
from quant_system.engine.portfolio import Portfolio
from quant_system.indicators.technical import add_indicators
from quant_system.performance.analyzer import PerformanceAnalyzer
from quant_system.strategies.dual_ma import DualMovingAverageStrategy


def frame() -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": ["000001.SZ"] * 6,
        "trade_date": pd.date_range("2024-01-01", periods=6),
        "open": [10, 10, 11, 12, 11, 10],
        "high": [10.5, 10.5, 11.5, 12.5, 11.5, 10.5],
        "low": [9.5, 9.5, 10.5, 11.5, 10.5, 9.5],
        "close": [10, 9, 11, 13, 10, 12],
        "volume": [100] * 6,
        "amount": [1000] * 6,
    })


def test_cleaner_duplicate_and_ohlc() -> None:
    raw = frame()
    raw = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
    raw.loc[1, "high"] = 8
    cleaned, report = MarketDataCleaner().clean(MarketData(raw, "test", "unadjusted", True))
    assert report.duplicate_rows == 1
    assert report.rejected_rows >= 1
    assert len(cleaned) == 2


def test_indicators_returns_and_ma() -> None:
    result = add_indicators(frame(), short_window=2, long_window=3)
    assert math.isclose(result.loc[1, "daily_return"], -0.1)
    assert math.isclose(result.loc[2, "sma_short"], 10.0)
    assert pd.isna(result.loc[1, "sma_long"])
    assert math.isclose(result.loc[2, "sma_long"], 10.0)


def test_buy_and_sell_signals() -> None:
    data = frame()
    enriched = add_indicators(data, 2, 3)
    signals = DualMovingAverageStrategy(2, 3).generate_signals(enriched)
    assert set(signals["side"]) == {"BUY", "SELL"}


def test_next_day_execution_and_costs() -> None:
    data = frame().iloc[:4].copy()
    signals = pd.DataFrame({"symbol": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "sma_short": [1.0], "sma_long": [0.5], "side": ["BUY"]})
    portfolio = Portfolio(10000, commission_rate=0.001, slippage_rate=0.01, lot_size=100)
    result = BacktestEngine(portfolio).run(data, signals)
    assert len(result.trades) == 1
    assert result.trades[0].trade_date == pd.Timestamp("2024-01-03").date()
    assert result.trades[0].price == pytest.approx(11.11)
    assert result.trades[0].commission > 0
    assert portfolio.position.quantity == 100


def test_insufficient_cash() -> None:
    portfolio = Portfolio(100, lot_size=100)
    assert portfolio.execute("BUY", 100, 10) is None
    assert portfolio.position.quantity == 0


def test_max_drawdown_and_sharpe() -> None:
    snapshots = pd.DataFrame({"total_value": [100, 120, 90, 110], "daily_return": [0, .2, -.25, .2222]})
    metrics = PerformanceAnalyzer(risk_free_rate=0).analyze(snapshots)
    assert metrics["max_drawdown"] == pytest.approx(-0.25)
    assert metrics["sharpe_ratio"] != 0
