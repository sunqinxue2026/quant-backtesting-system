from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from quant_system.database import DataImportBatch, StockDaily, create_session_factory
from quant_system.repository import MarketDataRepository

DATA = Path(__file__).parents[2] / "data/test/synthetic_cleaning_demo.csv"
HEADER = "symbol,trade_date,open,high,low,close,volume,amount\n"


def request(path=DATA):
    return DataLoadRequest(path, "synthetic/test", "2024-01-03", "前复权研究口径",
                           {"price": "CNY", "volume": "股", "amount": "CNY"}, True)


@pytest.fixture
def factory():
    value = create_session_factory("sqlite:///:memory:")
    yield value
    value.kw["bind"].dispose()


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_csv_cleaning_to_database_matches_accepted_and_preserves_metadata(factory):
    result = import_csv(request(), factory)
    assert result.inserted_rows == 2
    with factory() as session:
        batch = session.get(DataImportBatch, result.batch_id)
        assert batch.input_rows == 6 and batch.accepted_rows == 2
        assert batch.rejected_rows == 2 and batch.quality_status == "partial"
        assert batch.is_synthetic and batch.source == "synthetic/test"
        assert batch.data_as_of == date(2024, 1, 3)
        assert batch.units_json["volume"] == "股"
        quality = batch.units_json["_quality_report"]
        assert quality["review_rows"] == 1 and quality["duplicate_removed_rows"] == 1
        assert len(batch.units_json["_metadata"]["extra"]["file_sha256"]) == 64
        rows = MarketDataRepository(session).query_daily("000001.SZ", date(2024, 1, 1), date(2024, 1, 31), "前复权研究口径")
        expected = result.cleaning.accepted
        assert len(rows) == len(expected) == count(session, StockDaily)
        for actual, accepted in zip(rows, expected.itertuples(index=False)):
            assert actual.symbol == accepted.symbol and actual.trade_date == accepted.trade_date
            for column in ("open", "high", "low", "close", "volume", "amount"):
                assert getattr(actual, column) == Decimal(str(getattr(accepted, column)))
            assert actual.import_batch_id == batch.id
            assert actual.source == batch.source and actual.price_type == batch.price_type


def test_reimport_is_rejected_without_extra_batch_or_market_rows(factory):
    first = import_csv(request(), factory)
    with pytest.raises(IntegrityError):
        import_csv(request(), factory)
    with factory() as session:
        assert count(session, DataImportBatch) == 1
        assert count(session, StockDaily) == 2
        assert session.get(DataImportBatch, first.batch_id) is not None


def test_mid_batch_conflict_rolls_back_new_rows_and_import_batch(factory, tmp_path):
    import_csv(request(), factory)
    path = tmp_path / "conflict.csv"
    # 新股票先插入，第二行冲突，验证前一条也会回滚。
    path.write_text(HEADER + "000000.SZ,2024-01-02,10,12,9,11,100,1100\n"
                    + "000001.SZ,2024-01-02,10,12,9,11,100,1100\n", encoding="utf-8")
    with pytest.raises(IntegrityError):
        import_csv(request(path), factory)
    with factory() as session:
        assert count(session, StockDaily) == 2
        assert count(session, DataImportBatch) == 1
        assert MarketDataRepository(session).count_daily("000000.SZ") == 0


def test_no_accepted_rows_keeps_quality_batch_without_market_rows(factory, tmp_path):
    path = tmp_path / "review.csv"
    path.write_text(HEADER + "000001.SZ,2024-01-02,10,12,9,11,0,0\n", encoding="utf-8")
    result = import_csv(request(path), factory)
    assert result.inserted_rows == 0
    with factory() as session:
        assert count(session, StockDaily) == 0
        batch = session.get(DataImportBatch, result.batch_id)
        assert batch.quality_status == "no_accepted"
        assert batch.units_json["_quality_report"]["review_rows"] == 1


def test_invalid_metadata_does_not_create_batch(factory):
    bad = DataLoadRequest(DATA, "synthetic/test", "invalid", "未复权", {}, True)
    with pytest.raises(ValueError):
        import_csv(bad, factory)
    with factory() as session:
        assert count(session, DataImportBatch) == 0


def test_missing_csv_does_not_create_batch(factory, tmp_path):
    with pytest.raises(FileNotFoundError):
        import_csv(request(tmp_path / "missing.csv"), factory)
    with factory() as session:
        assert count(session, DataImportBatch) == 0
