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


def make_data(rows):
    from quant_system.data.models import DatasetMetadata, MarketData
    return MarketData(pd.DataFrame(rows), DatasetMetadata("synthetic/test", "memory", "2024-01-03", "未复权", {}, True))


def valid_row(**changes):
    row = dict(symbol="000001.SZ", trade_date="2024-01-02", open=10, high=12, low=9, close=11, volume=100, amount=1100)
    row.update(changes)
    return row


def test_all_rejections_preserve_source_and_counts():
    rows = [valid_row(trade_date="bad"), valid_row(symbol="bad"),
            valid_row(), valid_row(close=10), valid_row(symbol="000002.SZ", high=1)]
    result = MarketDataCleaner().clean(make_data(rows))
    assert len(result.rejected) == result.report.rejected_rows == 5
    assert set(result.rejected["_source_row"]) == set(range(1, 6))
    assert result.rejected["_reason"].ne("").all()
    assert result.rejected.loc[result.rejected["_reason"].eq("invalid_trade_date"), "_raw_trade_date"].iloc[0] == "bad"


def test_missing_value_does_not_disappear_in_duplicate_comparison():
    result = MarketDataCleaner().clean(make_data([valid_row(), valid_row(close=None)]))
    assert result.report.duplicate_removed_rows == 0
    assert len(result.rejected) == 2
    assert set(result.rejected["_reason"]) == {"conflicting_duplicate"}


def test_symbol_normalization_and_repair_count():
    result = MarketDataCleaner().clean(make_data([valid_row(symbol=" 000001.sz ")]))
    assert result.accepted["symbol"].tolist() == ["000001.SZ"]
    assert result.report.repaired_rows == 1
    assert result.accepted["_repaired"].all()


import pytest


@pytest.mark.parametrize("changes,reason", [
    ({"close": None}, "missing_or_non_numeric_value"),
    ({"volume": "bad"}, "missing_or_non_numeric_value"),
    ({"high": float("inf")}, "non_finite_value"),
    ({"amount": float("-inf")}, "non_finite_value"),
    ({"open": 0}, "invalid_ohlc_or_turnover"),
    ({"low": 11.5}, "invalid_ohlc_or_turnover"),
    ({"volume": -1}, "invalid_ohlc_or_turnover"),
    ({"amount": -1}, "invalid_ohlc_or_turnover"),
    ({"symbol": "000001"}, "invalid_symbol"),
])
def test_invalid_values(changes, reason):
    result = MarketDataCleaner().clean(make_data([valid_row(**changes)]))
    assert len(result.rejected) == 1
    assert result.rejected.iloc[0]["_reason"] == reason


def test_date_numeric_normalization_review_and_conservation():
    result = MarketDataCleaner().clean(make_data([
        valid_row(trade_date="2024/01/03", open="10"),
        valid_row(trade_date="2024-01-02", volume=0),
        valid_row(trade_date="2024-01-02", volume=0),
    ]))
    r = result.report
    assert r.input_rows == r.accepted_rows + r.review_rows + r.rejected_rows + r.duplicate_removed_rows
    assert len(result.review) == 1 and r.duplicate_removed_rows == 1
    assert result.accepted.iloc[0]["trade_date"] == pd.Timestamp("2024-01-03").date()
    assert result.accepted.iloc[0]["open"] == 10


def test_empty_frame_is_supported():
    from quant_system.data.models import REQUIRED_COLUMNS
    data = make_data([valid_row()])
    object.__setattr__(data, "frame", pd.DataFrame(columns=REQUIRED_COLUMNS))
    result = MarketDataCleaner().clean(data)
    assert result.report.input_rows == 0
    assert result.rejected.empty and result.accepted.empty
