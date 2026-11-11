from pathlib import Path

import pytest

from quant_system.data import CsvMarketDataSource, DataLoadRequest


DATA = Path(__file__).parents[2] / "data" / "test" / "synthetic_cleaning_demo.csv"


def request(path=DATA):
    return DataLoadRequest(path, "synthetic/test", "2024-01-03", "前复权研究口径", {"price": "CNY"}, True)


def test_csv_loader_maps_and_keeps_metadata():
    loaded = CsvMarketDataSource().load(request())
    assert list(loaded.frame.columns) == ["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]
    assert loaded.metadata.is_synthetic is True
    assert len(loaded.metadata.extra["file_sha256"]) == 64


def test_csv_loader_rejects_missing_column(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("symbol,trade_date,close\n000001.SZ,2024-01-01,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少必需字段"):
        CsvMarketDataSource().load(request(path))
