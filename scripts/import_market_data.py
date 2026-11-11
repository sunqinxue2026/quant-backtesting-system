"""第三阶段 CSV 清洗入库入口；连接地址仅从环境变量读取。"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from quant_system.database import create_session_factory


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="读取CSV、清洗并原子写入行情和导入批次")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--data-as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--price-type", required=True)
    parser.add_argument("--synthetic", action="store_true", help="明确标记合成测试数据")
    parser.add_argument("--price-unit", default="CNY")
    parser.add_argument("--volume-unit", default="股")
    parser.add_argument("--amount-unit", default="CNY")
    parser.add_argument("--output", type=Path, required=True, help="导入结果和清洗明细目录")
    args = parser.parse_args()
    request = DataLoadRequest(args.csv, args.source, args.data_as_of, args.price_type,
                              {"price": args.price_unit, "volume": args.volume_unit, "amount": args.amount_unit}, args.synthetic)
    factory = create_session_factory()
    try:
        result = import_csv(request, factory)
    except Exception:
        # 不输出 SQLAlchemy 异常文本，避免打印连接信息或完整行情参数。
        logger = logging.getLogger(__name__)
        logger.error("导入失败，事务未提交；检查文件、字段、日期、数据库连接及唯一键冲突。")
        raise SystemExit(1) from None
    finally:
        factory.kw["bind"].dispose()
    # DB 已提交；输出失败不会撤销已提交的数据，应使用 batch_id 查询，勿盲目重试。
    summary = {"batch_id": result.batch_id, "inserted_rows": result.inserted_rows,
               "status": "committed", "quality_report": result.cleaning.report.to_dict()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    try:
        args.output.mkdir(parents=True, exist_ok=True)
        for name in ("accepted", "review", "rejected"):
            getattr(result.cleaning, name).to_csv(args.output / f"{name}.csv", index=False)
        (args.output / "import_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logging.getLogger(__name__).error("数据库已提交 batch_id=%s，但报告写出失败；不要重复导入。", result.batch_id)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
