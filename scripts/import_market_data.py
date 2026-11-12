"""第三阶段 CSV 清洗入库入口；连接地址仅从环境变量读取。"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from quant_system.database import create_session_factory


def log_import_error(exc: Exception) -> None:
    """只输出固定分类和整数错误码，不输出异常正文、SQL或连接信息。"""
    logger = logging.getLogger(__name__)
    if isinstance(exc, SQLAlchemyError):
        original = getattr(exc, "orig", None)
        args = getattr(original, "args", ())
        code = args[0] if args and type(args[0]) is int else None
        code_text = str(code) if code is not None else "unknown"
        if isinstance(exc, IntegrityError):
            reason = "重复键冲突" if code == 1062 else "完整性约束冲突"
            logger.error("导入失败 type=IntegrityError db_code=%s reason=%s；导入事务未提交。", code_text, reason)
        elif isinstance(exc, OperationalError):
            logger.error("数据库操作失败 type=OperationalError db_code=%s；检查连接、权限或服务状态。", code_text)
        else:
            logger.error("数据库操作失败 type=SQLAlchemyError db_code=%s。", code_text)
    elif isinstance(exc, (ValueError, FileNotFoundError, OSError)):
        logger.error("导入失败 category=INPUT_ERROR；检查文件、字段、日期和文件权限。")
    else:
        logger.error("导入失败 category=UNEXPECTED_ERROR；需开发人员排查，未输出异常正文。")


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
    factory = None
    try:
        factory = create_session_factory()
        result = import_csv(request, factory)
    except Exception as exc:
        log_import_error(exc)
        raise SystemExit(1) from None
    finally:
        if factory is not None:
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
