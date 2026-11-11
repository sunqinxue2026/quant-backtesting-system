from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_system.data.models import MarketData, REQUIRED_COLUMNS
from .models import QualityReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanResult:
    accepted: pd.DataFrame
    review: pd.DataFrame
    rejected: pd.DataFrame
    report: QualityReport


class MarketDataCleaner:
    """按互斥终态分类；拒绝明细保留原始字段、来源记录号和原因。"""

    NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "amount")

    def clean(self, market_data: MarketData) -> CleanResult:
        raw = market_data.frame.reset_index(drop=True).copy()
        missing = set(REQUIRED_COLUMNS) - set(raw.columns)
        if missing:
            raise ValueError(f"缺少必需字段: {', '.join(sorted(missing))}")
        metadata = market_data.metadata
        report = QualityReport(input_rows=len(raw), metadata={
            "source": metadata.source_name, "source_file": metadata.source_file,
            "data_as_of": metadata.data_as_of, "adjustment_type": metadata.adjustment_type,
            "units": metadata.units, "is_synthetic": metadata.is_synthetic,
            "extra": metadata.extra,
            "calendar_status": "unknown_without_external_calendar",
        })
        frame = raw.loc[:, list(REQUIRED_COLUMNS)].copy()
        frame["_source_row"] = np.arange(1, len(frame) + 1)
        for column in REQUIRED_COLUMNS:
            frame[f"_raw_{column}"] = raw[column]
        original_symbol = frame["symbol"].astype("string")
        frame["symbol"] = original_symbol.str.strip().str.upper()
        repaired = original_symbol.ne(frame["symbol"]).fillna(False)
        frame["_repaired"] = repaired
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="mixed", errors="coerce").dt.date
        for column in self.NUMERIC_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["_row_status"] = "pending"
        frame["_reason"] = ""

        def reject(mask: pd.Series, reason: str) -> None:
            selected = mask & frame["_row_status"].eq("pending")
            frame.loc[selected, "_row_status"] = "rejected"
            frame.loc[selected, "_reason"] = reason
            if selected.any():
                report.add_reason(reason, int(selected.sum()))

        reject(frame["trade_date"].isna(), "invalid_trade_date")
        reject(~frame["symbol"].str.fullmatch(r"\d{6}\.(SH|SZ)", na=False), "invalid_symbol")

        # dropna=False 使缺失与非缺失不同，不能将冲突记录误删为相同记录。
        pending = frame.loc[frame["_row_status"].eq("pending")]
        key = ["symbol", "trade_date"]
        counts = pending.groupby(key)[list(self.NUMERIC_COLUMNS)].transform("nunique", dropna=False)
        conflict_indices = counts.index[counts.max(axis=1).gt(1)]
        reject(pd.Series(frame.index.isin(conflict_indices), index=frame.index), "conflicting_duplicate")
        pending = frame.loc[frame["_row_status"].eq("pending")]
        duplicates = pending.index[pending.duplicated(subset=key, keep="first")]
        frame.loc[duplicates, "_row_status"] = "duplicate_removed"
        frame.loc[duplicates, "_reason"] = "exact_duplicate"
        report.duplicate_removed_rows = len(duplicates)
        if len(duplicates):
            report.add_reason("exact_duplicate", len(duplicates))

        values = frame[list(self.NUMERIC_COLUMNS)]
        reject(values.isna().any(axis=1), "missing_or_non_numeric_value")
        finite = pd.Series(np.isfinite(values.to_numpy(dtype=float, na_value=np.nan)).all(axis=1), index=frame.index)
        reject(~finite, "non_finite_value")
        prices = frame[["open", "high", "low", "close"]]
        valid_ohlc = ((prices > 0).all(axis=1)
                      & frame["high"].ge(frame[["open", "close"]].max(axis=1))
                      & frame["low"].le(frame[["open", "close"]].min(axis=1))
                      & frame["high"].ge(frame["low"]))
        reject(~valid_ohlc | (frame[["volume", "amount"]] < 0).any(axis=1), "invalid_ohlc_or_turnover")
        pending_mask = frame["_row_status"].eq("pending")
        review_mask = pending_mask & (frame[["volume", "amount"]] == 0).any(axis=1)
        frame.loc[review_mask, "_row_status"] = "review"
        frame.loc[review_mask, "_reason"] = "zero_turnover_requires_review"
        frame.loc[frame["_row_status"].eq("pending"), "_row_status"] = "accepted"
        report.review_rows = int(review_mask.sum())
        if report.review_rows:
            report.add_reason("zero_turnover_requires_review", report.review_rows)
        report.repaired_rows = int(repaired.sum())
        report.rejected_rows = int(frame["_row_status"].eq("rejected").sum())
        report.accepted_rows = int(frame["_row_status"].eq("accepted").sum())
        report.output_rows = report.accepted_rows
        if report.input_rows != sum((report.accepted_rows, report.review_rows, report.rejected_rows, report.duplicate_removed_rows)):
            raise RuntimeError("清洗终态数量不守恒")

        def subset(status: str) -> pd.DataFrame:
            return frame.loc[frame["_row_status"].eq(status)].sort_values(key, na_position="last").reset_index(drop=True)

        logger.info("清洗完成 input=%d accepted=%d review=%d rejected=%d duplicates=%d",
                    report.input_rows, report.accepted_rows, report.review_rows,
                    report.rejected_rows, report.duplicate_removed_rows)
        return CleanResult(subset("accepted"), subset("review"), subset("rejected"), report)
