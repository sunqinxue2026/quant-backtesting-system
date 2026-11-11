from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DataLoadRequest:
    path: Path
    source_name: str
    data_as_of: str
    adjustment_type: str
    units: dict[str, str]
    is_synthetic: bool = False


@dataclass(frozen=True)
class DatasetMetadata:
    source_name: str
    source_file: str
    data_as_of: str
    adjustment_type: str
    units: dict[str, str]
    is_synthetic: bool
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketData:
    frame: pd.DataFrame
    metadata: DatasetMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.frame, pd.DataFrame):
            raise TypeError("frame 必须是 pandas.DataFrame")


REQUIRED_COLUMNS = ("symbol", "trade_date", "open", "high", "low", "close", "volume", "amount")
