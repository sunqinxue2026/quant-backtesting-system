from pathlib import Path

import pandas as pd

from quant_system.cleaning import MarketDataCleaner
from quant_system.data import CsvMarketDataSource, DataLoadRequest


DATA = Path(__file__).parents[2] / "data" / "test" / "synthetic_cleaning_demo.csv"


def load():
    return CsvMarketDataSource().load(DataLoadRequest(DATA, "synthetic/test", "2024-01-03", "前复权研究口径", {"price": "CNY"}, True))


def test_cleaner_identifies_quality_categories_and_sorts():
    result = MarketDataCleaner().clean(load())
    assert list(result.accepted["trade_date"]) == [pd.Timestamp("2024-01-02").date(), pd.Timestamp("2024-01-03").date()]
    assert result.report.input_rows == 6
    assert result.report.duplicate_removed_rows == 1
    assert result.report.rejected_rows == 2
    assert result.report.review_rows == 1
    assert result.report.accepted_rows == 2
    assert result.report.output_rows == result.report.accepted_rows
    assert result.report.metadata["is_synthetic"] is True


def test_conflicting_duplicate_is_rejected():
    frame = pd.DataFrame([
        {"symbol": "000001.SZ", "trade_date": "2024-01-01", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "amount": 15},
        {"symbol": "000001.SZ", "trade_date": "2024-01-01", "open": 1, "high": 3, "low": 1, "close": 2, "volume": 10, "amount": 20},
    ])
    from quant_system.data.models import DatasetMetadata, MarketData
    data = MarketData(frame, DatasetMetadata("test", "memory.csv", "2024-01-01", "未复权", {"price": "CNY"}, True))
    result = MarketDataCleaner().clean(data)
    assert result.report.rejected_rows == 2
    assert result.accepted.empty
    assert result.report.reasons["conflicting_duplicate"] == 2


def test_missing_and_invalid_ohlc_are_rejected():
    frame = pd.DataFrame([
        {"symbol": "000001.SZ", "trade_date": "bad", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "amount": 15},
        {"symbol": "000002.SZ", "trade_date": "2024-01-01", "open": 2, "high": 1, "low": 1.5, "close": 1.8, "volume": 10, "amount": 18},
    ])
    from quant_system.data.models import DatasetMetadata, MarketData
    data = MarketData(frame, DatasetMetadata("test", "memory.csv", "2024-01-01", "未复权", {"price": "CNY"}, True))
    result = MarketDataCleaner().clean(data)
    assert result.report.rejected_rows == 2
    assert result.accepted.empty
