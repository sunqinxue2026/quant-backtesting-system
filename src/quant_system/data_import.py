from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN

from sqlalchemy.orm import Session, sessionmaker

from .cleaning.cleaner import CleanResult, MarketDataCleaner
from .data import CsvMarketDataSource, DataLoadRequest
from .database import DataImportBatch, StockDaily
from .repository import MarketDataRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    inserted_rows: int
    cleaning: CleanResult


def import_csv(request: DataLoadRequest, factory: sessionmaker[Session]) -> ImportResult:
    """读取并清洗 CSV；仅 accepted 入库，批次和行情在同一事务提交。

    唯一键冲突直接抛出 IntegrityError，整批回滚，不覆盖已有数据。
    无 accepted 行时仍保存零行情的批次以记录质量结果。
    """
    if not request.source_name.strip() or not request.adjustment_type.strip():
        raise ValueError("必须提供数据来源和价格口径")
    data_as_of = date.fromisoformat(request.data_as_of)
    market_data = CsvMarketDataSource().load(request)
    cleaned = MarketDataCleaner().clean(market_data)
    report = cleaned.report
    # 沿用现有批次 JSON 字段保存完整元信息，避免 create_all 无法升级已有表。
    metadata = dict(report.metadata)
    batch = DataImportBatch(
        source=request.source_name,
        source_file=market_data.metadata.source_file,
        data_as_of=data_as_of,
        price_type=request.adjustment_type,
        units_json={**request.units, "_metadata": metadata, "_quality_report": report.to_dict()},
        is_synthetic=request.is_synthetic,
        input_rows=report.input_rows,
        accepted_rows=report.accepted_rows,
        rejected_rows=report.rejected_rows,
        quality_status="accepted" if report.accepted_rows == report.input_rows else "partial" if report.accepted_rows else "no_accepted",
    )
    with factory.begin() as session:
        repo = MarketDataRepository(session)
        repo.add_import_batch(batch)
        rows = []
        for row in cleaned.accepted.itertuples(index=False):
            values = {
                column: Decimal(str(getattr(row, column))).quantize(
                    Decimal("0.0001") if column in ("volume", "amount") else Decimal("0.000001"),
                    rounding=ROUND_HALF_EVEN,
                )
                for column in MarketDataCleaner.NUMERIC_COLUMNS
            }
            rows.append(StockDaily(
                symbol=row.symbol, trade_date=row.trade_date, **values,
                source=request.source_name, price_type=request.adjustment_type,
                import_batch_id=batch.id,
            ))
        inserted = repo.bulk_insert_daily(rows)
        batch_id = batch.id
    logger.info("导入提交成功 batch_id=%d inserted=%d", batch_id, inserted)
    return ImportResult(batch_id, inserted, cleaned)
