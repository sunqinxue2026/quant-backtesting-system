"""第七阶段：可重复的真实CSV到绩效报告演示；不下载行情、不创建MySQL数据库。"""
from __future__ import annotations
import argparse
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sqlalchemy import select
from quant_system.database import create_session_factory, DataImportBatch, BacktestResult, BacktestSignal
from quant_system.data import DataLoadRequest, CsvMarketDataSource
from quant_system.cleaning import MarketDataCleaner
from quant_system.data_import import import_csv
from quant_system.backtest_pipeline import BacktestRequest, run_batch_backtest, load_batch_frame
from quant_system.engine import CostModel
from quant_system.engine.persistence import query_execution
from quant_system.performance import generate_report


def report_values_equal(expected, actual):
    """JSON回读：浮点允许序列化末位误差，其他类型、键和列表长度精确匹配。"""
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            report_values_equal(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            report_values_equal(a, b) for a, b in zip(expected, actual))
    if isinstance(expected, float):
        return math.isfinite(expected) and math.isfinite(actual) and math.isclose(
            expected, actual, rel_tol=1e-12, abs_tol=1e-14)
    return expected == actual


def run_demo(csv_path, provenance_path, factory, output, *, short=5, long=20, cash=Decimal('100000'), quantity=100):
    csv_path, output = Path(csv_path), Path(output)
    provenance = json.loads(Path(provenance_path).read_text(encoding='utf-8'))
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if digest != provenance['csv_sha256']:
        raise ValueError('CSV摘要与来源说明不一致')
    if provenance.get('is_synthetic') is not False:
        raise ValueError('真实演示要求is_synthetic=false的来源说明')
    units = provenance['units']
    request = DataLoadRequest(csv_path, provenance['source'], provenance['data_as_of'], provenance['price_type'], units, False)
    cleaned = MarketDataCleaner().clean(CsvMarketDataSource().load(request))
    if cleaned.accepted.empty:
        raise ValueError('没有accepted行情')
    if set(cleaned.accepted.symbol) != {provenance['symbol']}:
        raise ValueError('CSV股票与来源说明不一致或包含多股票')
    output.mkdir(parents=True, exist_ok=True)
    for name in ('accepted', 'review', 'rejected'):
        getattr(cleaned, name).to_csv(output / f'{name}.csv', index=False)
    (output / 'quality_report.json').write_text(json.dumps(cleaned.report.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    with factory() as session:
        candidates = list(session.scalars(select(DataImportBatch).where(
            DataImportBatch.source == request.source_name,
            DataImportBatch.price_type == request.adjustment_type)))
        matches = [b for b in candidates if not b.is_synthetic and b.units_json.get('_metadata', {}).get('extra', {}).get('file_sha256') == digest and all(b.units_json.get(k) == v for k,v in units.items()) and str(b.data_as_of) == request.data_as_of]
        batch_id = matches[0].id if matches else None
    reused = batch_id is not None
    if batch_id is None:
        batch_id = import_csv(request, factory).batch_id
    start, end = min(cleaned.accepted.trade_date), max(cleaned.accepted.trade_date)
    backtest_request = BacktestRequest(batch_id, provenance['symbol'], start, end, request.adjustment_type, cash, short, long, quantity)
    with factory() as session:
        loaded = load_batch_frame(session, backtest_request)
        expected = cleaned.accepted.sort_values(['symbol', 'trade_date']).reset_index(drop=True)
        if len(loaded) != len(expected):
            raise ValueError('已有批次行情数量与CSV不一致')
        for a,b in zip(loaded.itertuples(index=False), expected.itertuples(index=False)):
            if a.symbol != b.symbol or a.trade_date != b.trade_date:
                raise ValueError('批次行情身份不一致')
            for col in ('open','high','low','close','volume','amount'):
                tolerance = Decimal('0.000001') if col in ('open','high','low','close') else Decimal('0.0001')
                if abs(Decimal(str(getattr(a,col))) - Decimal(str(getattr(b,col)))) > tolerance:
                    raise ValueError('批次行情数值与CSV不一致')
    result = run_batch_backtest(backtest_request, factory, CostModel())
    payload = generate_report(factory, result.task_id, output)
    with factory() as session:
        saved = session.scalar(select(BacktestResult).where(BacktestResult.task_id == result.task_id))
        execution = query_execution(session, result.task_id)
        signals = list(session.scalars(select(BacktestSignal).where(BacktestSignal.task_id == result.task_id)))
        if saved is None or not report_values_equal(payload, saved.metrics_json):
            raise ValueError('数据库绩效JSON回读不一致')
        if [len(execution[k]) for k in ('orders','trades','snapshots')] != [len(result.execution.orders),len(result.execution.trades),len(result.execution.snapshots)]:
            raise ValueError('执行数量回读不一致')
        for stored, memory in zip(execution['snapshots'], result.execution.snapshots):
            if (stored.trade_date, stored.cash, stored.position_quantity, stored.total_value) != (memory.trade_date, memory.cash, memory.position_quantity, memory.total_value):
                raise ValueError('逐日快照回读不一致')
        if len(signals) != len(result.signals):
            raise ValueError('信号数量回读不一致')
    summary = dict(task_id=result.task_id, batch_id=batch_id, reused_batch=reused,
        quality=cleaned.report.to_dict(), signals=len(signals), orders=len(result.execution.orders),
        trades=len(result.execution.trades), snapshots=len(result.execution.snapshots),
        metrics=payload['metrics'], database_readback='passed', csv_sha256=digest,
        provenance=provenance, database_dialect=factory.kw['bind'].dialect.name)
    (output / 'verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--database', choices=['sqlite','configured'], default='sqlite')
    parser.add_argument('--output', type=Path, default=ROOT/'reports'/'stage7')
    parser.add_argument('--short', type=int, default=5)
    parser.add_argument('--long', type=int, default=20)
    parser.add_argument('--cash', type=Decimal, default=Decimal('100000'))
    parser.add_argument('--quantity', type=int, default=100)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.database == 'configured':
        url = os.getenv('DATABASE_URL')
        if not url:
            parser.error('configured模式要求DATABASE_URL')
    else:
        url = 'sqlite:///' + (args.output.resolve()/'demo.db').as_posix()
    folder = args.output / (datetime.now().strftime('run_%Y%m%d_%H%M%S_') + uuid4().hex[:8])
    factory = None
    try:
        factory = create_session_factory(url)
        summary = run_demo(args.csv, args.provenance, factory, folder,
            short=args.short, long=args.long, cash=args.cash, quantity=args.quantity)
        print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    except Exception as exc:
        logging.error('最终演示失败 type=%s；检查来源、参数和数据库。已提交行情保留，不输出连接串。', type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        if factory is not None:
            factory.kw['bind'].dispose()

if __name__ == '__main__':
    main()
