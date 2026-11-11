from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]

@dataclass(frozen=True)
class MarketData:
    frame: pd.DataFrame
    source: str
    price_type: str
    is_synthetic: bool = False

class CsvMarketDataSource:
    """CSV 行情适配器，保持数据源与业务模块解耦。"""
    def load(self, path: str | Path, *, price_type: str = "forward_adjusted", is_synthetic: bool = False) -> MarketData:
        file_path = Path(path)
        frame = pd.read_csv(file_path)
        return MarketData(frame=frame, source=str(file_path), price_type=price_type, is_synthetic=is_synthetic)
