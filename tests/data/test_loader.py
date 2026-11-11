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


@pytest.mark.parametrize("text", ["", "   ", "symbol,trade_date,open,high,low,close,volume,amount\n"])
def test_empty_files_rejected(tmp_path, text):
    path = tmp_path / "empty.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        CsvMarketDataSource().load(request(path))


def test_missing_file_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        CsvMarketDataSource().load(request(tmp_path / "missing.csv"))


def test_aliases_preserve_leading_zero(tmp_path):
    path = tmp_path / "alias.csv"
    path.write_text(" 股票代码 ,日期,开盘,最高,最低,收盘,成交量,成交额\n000001,2024-01-02,10,12,9,11,100,1100\n", encoding="utf-8")
    loaded = CsvMarketDataSource().load(request(path))
    assert loaded.frame.iloc[0]["symbol"] == "000001"
    assert loaded.metadata.source_name == "synthetic/test"


def test_colliding_aliases_rejected(tmp_path):
    path = tmp_path / "collision.csv"
    path.write_text("symbol,code,trade_date,open,high,low,close,volume,amount\n000001.SZ,000001.SZ,2024-01-02,10,12,9,11,100,1100\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重复列名"):
        CsvMarketDataSource().load(request(path))
