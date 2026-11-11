from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from .models import DataLoadRequest, DatasetMetadata, MarketData, REQUIRED_COLUMNS


_COLUMN_ALIASES = {
    "code": "symbol", "股票代码": "symbol", "证券代码": "symbol",
    "date": "trade_date", "日期": "trade_date", "交易日期": "trade_date",
    "开盘": "open", "开盘价": "open", "最高": "high", "最高价": "high",
    "最低": "low", "最低价": "low", "收盘": "close", "收盘价": "close",
    "成交量": "volume", "成交额": "amount",
}


class CsvMarketDataSource:
    """CSV 行情适配器，只负责读取和封装来源元信息。"""

    def load(self, request: DataLoadRequest) -> MarketData:
        path = Path(request.path)
        if not path.exists():
            raise FileNotFoundError(f"行情文件不存在: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"行情文件为空: {path}")

        frame = pd.read_csv(path)
        frame.columns = [self._normalise_column(str(column)) for column in frame.columns]
        missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"CSV 缺少必需字段: {', '.join(missing)}")

        metadata = DatasetMetadata(
            source_name=request.source_name,
            source_file=path.name,
            data_as_of=request.data_as_of,
            adjustment_type=request.adjustment_type,
            units=dict(request.units),
            is_synthetic=request.is_synthetic,
            extra={"file_sha256": self._sha256(path)},
        )
        return MarketData(frame=frame, metadata=metadata)

    @staticmethod
    def _normalise_column(column: str) -> str:
        key = column.strip().lower().replace(" ", "_")
        return _COLUMN_ALIASES.get(key, key)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
