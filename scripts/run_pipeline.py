"""第五阶段统一入口：CSV导入或已有批次 -> 回测 -> 执行记录入库。"""
from __future__ import annotations
import argparse
from datetime import date
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from quant_system.database import create_session_factory
from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from quant_system.backtest_pipeline import BacktestRequest, run_batch_backtest
from quant_system.engine import CostModel


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='第五阶段完整数据链路，不含绩效图表')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--csv', type=Path)
    group.add_argument('--batch-id', type=int)
    parser.add_argument('--database', choices=['demo', 'configured'], default='demo')
    parser.add_argument('--source')
    parser.add_argument('--data-as-of')
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--price-type', required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    parser.add_argument('--short', type=int, default=2)
    parser.add_argument('--long', type=int, default=3)
    parser.add_argument('--cash', type=Decimal, default=Decimal('10000'))
    parser.add_argument('--quantity', type=int, default=100)
    parser.add_argument('--zero-cost', action='store_true', help='仅用于手算测试，关闭全部成本')
    args = parser.parse_args()
    if args.csv and (not args.source or not args.data_as_of):
        parser.error('CSV模式必须提供--source和--data-as-of')
    if args.database == 'configured':
        url = os.getenv('DATABASE_URL')
        if not url:
            parser.error('configured模式要求已设置DATABASE_URL')
    else:
        folder = ROOT / 'reports' / 'stage5_pipeline'
        folder.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{folder / 'demo.db'}"
    factory = create_session_factory(url)
    try:
        batch_id = args.batch_id
        if args.csv:
            path = args.csv if args.csv.is_absolute() else ROOT / args.csv
            batch_id = import_csv(DataLoadRequest(path, args.source, args.data_as_of,
                args.price_type, {'price': 'CNY', 'volume': '股', 'amount': 'CNY'}, args.synthetic), factory).batch_id
        costs = CostModel(commission_rate=0, minimum_commission=0, stamp_tax_rate=0, slippage_bps=0) if args.zero_cost else CostModel()
        result = run_batch_backtest(BacktestRequest(batch_id, args.symbol, args.start, args.end,
            args.price_type, args.cash, args.short, args.long, args.quantity), factory, costs)
        print(json.dumps({'task_id': result.task_id, 'batch_id': result.batch_id,
            'signals': len(result.signals), 'orders': len(result.execution.orders),
            'trades': len(result.execution.trades), 'snapshots': len(result.execution.snapshots),
            'final_value': str(result.execution.final_value)}, ensure_ascii=False, indent=2))
    except Exception as exc:
        logging.error('回测流程失败 type=%s；检查输入和数据库约束。已提交的行情导入不会因回测失败而撤销。', type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        factory.kw['bind'].dispose()


if __name__ == '__main__':
    main()
