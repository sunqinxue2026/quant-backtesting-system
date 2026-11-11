from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd

REQUIRED_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]


@dataclass(frozen=True)
class DataLoadRequest:
    path: str | Path
    price_type: str = "forward_adjusted"
    volume_unit: str = "share"
    amount_unit: str = "currency"
    is_synthetic: bool = False


@dataclass(frozen=True)
class MarketData:
    frame: pd.DataFrame
    source: str
    price_type: str
    is_synthetic: bool = False
    volume_unit: str = "share"
    amount_unit: str = "currency"
    metadata: dict[str, str] = field(default_factory=dict)


class MarketDataSource(Protocol):
    def load(self, request: DataLoadRequest) -> MarketData: ...


class CsvMarketDataSource:
    """CSV 行情适配器；数据源层不依赖策略和回测。"""

    def load(
        self,
        path: str | Path | DataLoadRequest,
        *,
        price_type: str = "forward_adjusted",
        is_synthetic: bool = False,
        volume_unit: str = "share",
        amount_unit: str = "currency",
    ) -> MarketData:
        request = path if isinstance(path, DataLoadRequest) else DataLoadRequest(
            path, price_type, volume_unit, amount_unit, is_synthetic
        )
        file_path = Path(request.path)
        frame = pd.read_csv(file_path)
        dates = pd.to_datetime(frame["trade_date"], errors="coerce") if "trade_date" in frame else pd.Series(dtype="datetime64[ns]")
        metadata = {
            "source_file": file_path.name,
            "data_as_of": dates.max().strftime("%Y-%m-%d") if not dates.dropna().empty else "",
            "adjustment_type": request.price_type,
            "volume_unit": request.volume_unit,
            "amount_unit": request.amount_unit,
            "data_quality_status": "raw",
        }
        return MarketData(frame, str(file_path), request.price_type, request.is_synthetic, request.volume_unit, request.amount_unit, metadata)
