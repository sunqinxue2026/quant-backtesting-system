from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quant_system.data.models import MarketData, REQUIRED_COLUMNS

from .models import QualityReport


@dataclass(frozen=True)
class CleanResult:
    accepted: pd.DataFrame
    review: pd.DataFrame
    rejected: pd.DataFrame
    report: QualityReport


class MarketDataCleaner:
    """把原始行情转换为可审查的标准化数据，不静默修复关键缺失值。"""

    NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "amount")

    def clean(self, market_data: MarketData) -> CleanResult:
        raw = market_data.frame.copy()
        report = QualityReport(input_rows=len(raw), metadata={"source": market_data.metadata.source_name, "source_file": market_data.metadata.source_file, "data_as_of": market_data.metadata.data_as_of, "adjustment_type": market_data.metadata.adjustment_type, "units": market_data.metadata.units, "is_synthetic": market_data.metadata.is_synthetic})
        frame = raw.loc[:, list(REQUIRED_COLUMNS)].copy()
        frame["symbol"] = frame["symbol"].astype("string").str.strip()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="mixed", errors="coerce").dt.date
        for column in self.NUMERIC_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        invalid_date = frame["trade_date"].isna()
        if invalid_date.any():
            report.rejected_rows += int(invalid_date.sum())
            report.add_reason("invalid_trade_date", int(invalid_date.sum()))
        frame = frame.loc[~invalid_date].copy()

        invalid_symbol = ~frame["symbol"].str.fullmatch(r"\d{6}\.(SH|SZ)", na=False)
        if invalid_symbol.any():
            report.rejected_rows += int(invalid_symbol.sum())
            report.add_reason("invalid_symbol", int(invalid_symbol.sum()))
        frame = frame.loc[~invalid_symbol].copy()

        key = ["symbol", "trade_date"]
        conflict_keys = frame.groupby(key, dropna=False).size()
        duplicate_key_values = set(conflict_keys[conflict_keys > 1].index.tolist())
        conflict_mask = frame.set_index(key).index.isin(duplicate_key_values) if duplicate_key_values else np.zeros(len(frame), dtype=bool)
        duplicate_group = frame.loc[conflict_mask].copy()
        if not duplicate_group.empty:
            duplicate_group["_row_status"] = "duplicate_candidate"
            same_values = duplicate_group.groupby(key, dropna=False)[list(self.NUMERIC_COLUMNS)].transform("nunique").max(axis=1).eq(1)
            exact_mask = conflict_mask.copy()
            exact_indices = duplicate_group.index[same_values].tolist()
            exact_mask = frame.index.isin(exact_indices)
            exact_rows = frame.loc[exact_mask].drop_duplicates(subset=key, keep="first")
            report.duplicate_removed_rows += len(exact_indices) - len(exact_rows)
            if report.duplicate_removed_rows:
                report.add_reason("exact_duplicate", report.duplicate_removed_rows)
            conflict_indices = duplicate_group.index[~same_values].tolist()
            report.rejected_rows += len(conflict_indices)
            if conflict_indices:
                report.add_reason("conflicting_duplicate", len(conflict_indices))
            frame = frame.loc[~frame.index.isin(exact_indices + conflict_indices)].copy()
            frame = pd.concat([frame, exact_rows], ignore_index=True)

        required_values = list(self.NUMERIC_COLUMNS)
        missing_price = frame[required_values].isna().any(axis=1)
        if missing_price.any():
            report.rejected_rows += int(missing_price.sum())
            report.add_reason("missing_or_non_numeric_value", int(missing_price.sum()))

        finite = np.isfinite(frame[required_values].to_numpy(dtype=float, na_value=np.nan)).all(axis=1)
        non_finite = ~finite & ~missing_price.to_numpy()
        if non_finite.any():
            report.rejected_rows += int(non_finite.sum())
            report.add_reason("non_finite_value", int(non_finite.sum()))

        valid_values = ~missing_price & ~pd.Series(non_finite, index=frame.index)
        positive_price = (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
        ohlc_valid = (
            (frame["high"] >= frame[["open", "close"]].max(axis=1))
            & (frame["low"] <= frame[["open", "close"]].min(axis=1))
            & (frame["high"] >= frame["low"])
        )
        non_negative_turnover = (frame[["volume", "amount"]] >= 0).all(axis=1)
        invalid_logic = valid_values & (~positive_price | ~ohlc_valid | ~non_negative_turnover)
        if invalid_logic.any():
            report.rejected_rows += int(invalid_logic.sum())
            report.add_reason("invalid_ohlc_or_turnover", int(invalid_logic.sum()))

        rejected_mask = missing_price | pd.Series(non_finite, index=frame.index) | invalid_logic
        valid = frame.loc[~rejected_mask].copy()
        review_mask = (valid["volume"] == 0) | (valid["amount"] == 0)
        review = valid.loc[review_mask].copy()
        accepted = valid.loc[~review_mask].copy()
        report.review_rows = len(review)
        report.accepted_rows = len(accepted)
        report.output_rows = len(accepted)
        if report.review_rows:
            report.add_reason("zero_turnover_requires_review", report.review_rows)
        report.repaired_rows = 0
        accepted = accepted.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
        review = review.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
        return CleanResult(accepted=accepted, review=review, rejected=frame.loc[rejected_mask].copy(), report=report)
