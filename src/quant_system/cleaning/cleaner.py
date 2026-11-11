from __future__ import annotations

from dataclasses import dataclass, field, asdict
import logging
import re

import pandas as pd

from quant_system.data.loader import REQUIRED_COLUMNS, MarketData

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    input_rows: int
    output_rows: int = 0
    repaired_rows: int = 0
    duplicate_rows: int = 0
    conflicting_duplicate_rows: int = 0
    rejected_rows: int = 0
    review_rows: int = 0
    source: str = ""
    price_type: str = ""
    volume_unit: str = ""
    amount_unit: str = ""
    data_as_of: str = ""
    is_synthetic: bool = False
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class MarketDataCleaner:
    def clean(self, market_data: MarketData) -> tuple[pd.DataFrame, QualityReport]:
        raw = market_data.frame.copy()
        report = QualityReport(
            input_rows=len(raw), source=market_data.source, price_type=market_data.price_type,
            volume_unit=market_data.volume_unit, amount_unit=market_data.amount_unit,
            data_as_of=market_data.metadata.get("data_as_of", ""), is_synthetic=market_data.is_synthetic,
        )
        raw.columns = [str(c).strip().lower() for c in raw.columns]
        missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
        if missing:
            raise ValueError(f"缺少必需字段: {missing}")
        df = raw[REQUIRED_COLUMNS].copy()
        before_symbol = df["symbol"].astype(str)
        df["symbol"] = before_symbol.str.upper().str.strip()
        report.repaired_rows += int((before_symbol != df["symbol"]).sum())
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        numeric = ["open", "high", "low", "close", "volume", "amount"]
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        invalid_date = df["trade_date"].isna()
        report.rejected_rows += int(invalid_date.sum())
        if invalid_date.any():
            report.issues.append("存在无法解析的交易日期，已拒绝")
        df = df.loc[~invalid_date].copy()
        key = ["symbol", "trade_date"]
        duplicated = df.duplicated(key, keep=False)
        conflicting = df.loc[duplicated].groupby(key)[numeric].nunique().max(axis=1).gt(1)
        report.conflicting_duplicate_rows = int(conflicting.sum())
        if report.conflicting_duplicate_rows:
            report.rejected_rows += report.conflicting_duplicate_rows
            report.issues.append("同代码同日期存在数值冲突记录，已拒绝冲突组")
            conflict_keys = set(conflicting[conflicting].index)
            df = df.loc[~df.set_index(key).index.isin(conflict_keys)].reset_index(drop=True)
        duplicate_mask = df.duplicated(key, keep="first")
        report.duplicate_rows = int(duplicate_mask.sum())
        df = df.loc[~duplicate_mask].copy()
        invalid_symbol = ~df["symbol"].str.match(r"^\d{6}\.(SH|SZ)$")
        if invalid_symbol.any():
            report.rejected_rows += int(invalid_symbol.sum())
            report.issues.append("存在非沪深普通股票代码，已拒绝")
        missing_value = df[numeric].isna().any(axis=1)
        non_positive = (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        ohlc_invalid = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        volume_invalid = (df["volume"] < 0) | (df["amount"] < 0)
        reject = invalid_symbol | missing_value | non_positive | ohlc_invalid | volume_invalid
        report.rejected_rows += int(reject.sum())
        if reject.any():
            report.issues.append("存在缺失数值、代码格式、非正价格、OHLC 或成交量/成交额错误，已拒绝")
        df = df.loc[~reject].sort_values(key).reset_index(drop=True)
        df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
        report.output_rows = len(df)
        logger.info("行情清洗完成: %s -> %s", report.input_rows, report.output_rows)
        return df, report
