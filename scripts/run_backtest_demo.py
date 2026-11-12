"""第五阶段确定性 synthetic/test 演示，不连接数据库，不代表市场收益。"""
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import json
import logging
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import pandas as pd
from quant_system.indicators import add_indicators
from quant_system.strategies import DualMovingAverageStrategy
from quant_system.engine import BacktestEngine, CostModel


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    frame = pd.DataFrame({
        'symbol': ['000001.SZ'] * 9,
        'trade_date': pd.bdate_range('2024-01-02', periods=9),
        'open': [10,9,8,9,10,11,10,9,8],
        'close': [10,9,8,9,10,11,10,9,8],
        'volume': [100] * 9,
    })
    indicators = add_indicators(frame, short_window=2, long_window=3)
    costs = CostModel(commission_rate=0, minimum_commission=0, stamp_tax_rate=0, slippage_bps=0)
    result = BacktestEngine(DualMovingAverageStrategy(2,3), Decimal('10000'), costs, order_quantity=100).run(indicators)
    payload = {'source': 'synthetic/test', 'is_synthetic': True,
        'assumptions': '固定100股、无成本、下条有效日行情开盘执行；仅验证引擎，不模拟真实交易日历',
        'orders': [asdict(x) for x in result.orders],
        'trades': [asdict(x) for x in result.trades],
        'snapshots': [asdict(x) for x in result.snapshots],
        'final_cash': result.final_cash, 'final_position': result.final_position,
        'final_value': result.final_value}
    output = ROOT / 'reports' / 'stage5_demo'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'execution.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    pd.DataFrame(payload['snapshots']).to_csv(output / 'snapshots.csv', index=False)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
