from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from quant_system.cleaning import MarketDataCleaner
from quant_system.data import CsvMarketDataSource, DataLoadRequest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="第二阶段：读取和清洗 CSV 行情")
    parser.add_argument("csv", nargs="?", default="data/test/synthetic_cleaning_demo.csv")
    parser.add_argument("--source", default="synthetic/test")
    parser.add_argument("--data-as-of", default="2024-01-03")
    parser.add_argument("--adjustment-type", default="前复权研究口径")
    parser.add_argument("--output", default="reports/cleaning_demo")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    request = DataLoadRequest(csv_path, args.source, args.data_as_of, args.adjustment_type, {"price": "CNY", "volume": "股", "amount": "CNY"}, args.source == "synthetic/test")
    market_data = CsvMarketDataSource().load(request)
    result = MarketDataCleaner().clean(market_data)
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    result.accepted.to_csv(output / "cleaned.csv", index=False)
    result.review.to_csv(output / "review.csv", index=False)
    result.rejected.to_csv(output / "rejected.csv", index=False)
    (output / "quality_report.json").write_text(json.dumps(result.report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result.report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
