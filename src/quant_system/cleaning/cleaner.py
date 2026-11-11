from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging
import pandas as pd

from quant_system.data.loader import REQUIRED_COLUMNS, MarketData

logger = logging.getLogger(__name__)

@dataclass
class QualityReport:
    input_rows: int
    output_rows: int = 0
    repaired_rows: int = 0
    duplicate_rows: int = 0
    rejected_rows: int = 0
    review_rows: int = 0
    issues: list[str] = field(default_factory=list)

class MarketDataCleaner:
    def clean(self, market_data: MarketData) -> tuple[pd.DataFrame, QualityReport]:
        raw = market_data.frame.copy()
        report = QualityReport(input_rows=len(raw))
        missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
        if missing:
            raise ValueError(f"缺少必需字段: {missing}")
        df = raw[REQUIRED_COLUMNS].copy()
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        numeric = ["open", "high", "low", "close", "volume", "amount"]
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        invalid_date = df["trade_date"].isna()
        if invalid_date.any():
            report.rejected_rows += int(invalid_date.sum())
            report.issues.append("存在无法解析的交易日期，已拒绝")
        df = df.loc[~invalid_date].copy()
        duplicate_mask = df.duplicated(["symbol", "trade_date"], keep="first")
        report.duplicate_rows = int(duplicate_mask.sum())
        df = df.loc[~duplicate_mask].copy()
        missing_value = df[numeric].isna().any(axis=1)
        non_positive = (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        ohlc_invalid = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        volume_invalid = (df["volume"] < 0) | (df["amount"] < 0)
        reject = missing_value | non_positive | ohlc_invalid | volume_invalid
        report.rejected_rows += int(reject.sum())
        if reject.any():
            report.issues.append("存在缺失数值、非正价格、OHLC 逻辑错误或负成交量/成交额，已拒绝")
        df = df.loc[~reject].sort_values(["symbol", "trade_date"]).reset_index(drop=True)
        df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
        report.output_rows = len(df)
        logger.info("行情清洗完成: %s -> %s", report.input_rows, report.output_rows)
        return df, report
