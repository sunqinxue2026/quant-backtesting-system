"""第五阶段跨模块编排；不计算绩效，不执行真实交易。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging

import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from .database import DataImportBatch, StrategyConfig, BacktestTask, BacktestSignal
from .repository import MarketDataRepository
from .indicators import add_indicators
from .strategies import DualMovingAverageStrategy
from .engine import BacktestEngine, BacktestResult, CostModel
from .engine.persistence import save_execution

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestRequest:
    batch_id: int
    symbol: str
    start: date
    end: date
    price_type: str
    initial_cash: Decimal = Decimal('10000')
    short_window: int = 2
    long_window: int = 3
    order_quantity: int | None = 100


@dataclass(frozen=True)
class PipelineResult:
    task_id: int
    batch_id: int
    signals: pd.DataFrame
    execution: BacktestResult


def load_batch_frame(session: Session, request: BacktestRequest) -> pd.DataFrame:
    """验证批次身份，并将该批次 ORM 行情转换为标准数据帧。"""
    if request.start > request.end:
        raise ValueError('开始日期不能晚于结束日期')
    batch = session.get(DataImportBatch, request.batch_id)
    if batch is None or batch.price_type != request.price_type:
        raise ValueError('数据批次不存在或价格口径不一致')
    if not batch.accepted_rows:
        raise ValueError('批次没有accepted行情')
    units = batch.units_json
    if any(units.get(k) != v for k, v in {'price': 'CNY', 'volume': '股', 'amount': 'CNY'}.items()):
        raise ValueError('回测要求CNY价格、股成交量及CNY成交额，当前不自动换算单位')
    rows = MarketDataRepository(session).query_daily(
        request.symbol, request.start, request.end, request.price_type, request.batch_id)
    if not rows:
        raise ValueError('指定批次和区间没有行情')
    columns = ['symbol', 'trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount']
    frame = pd.DataFrame([{key: getattr(row, key) for key in columns} for row in rows])
    for column in columns[2:]:
        frame[column] = pd.to_numeric(frame[column], errors='raise')
    return frame


def run_batch_backtest(request: BacktestRequest, factory: sessionmaker[Session],
                       costs: CostModel | None = None) -> PipelineResult:
    """读取已提交行情，运行回测；所有新执行记录在单一事务内保存。"""
    strategy = DualMovingAverageStrategy(request.short_window, request.long_window)
    costs = costs or CostModel()
    with factory() as session:
        frame = load_batch_frame(session, request)
    indicators = add_indicators(frame, short_window=request.short_window, long_window=request.long_window)
    signals = strategy.generate_signals(indicators)
    result = BacktestEngine(strategy, request.initial_cash, costs, request.order_quantity).run(indicators)
    params = {
        'short_window': request.short_window, 'long_window': request.long_window,
        'order_quantity': request.order_quantity, 'start': request.start.isoformat(),
        'end': request.end.isoformat(), 'price_type': request.price_type,
        'costs': {k: str(getattr(costs, k)) for k in ('commission_rate', 'minimum_commission', 'stamp_tax_rate', 'slippage_bps')},
        'lot_size': costs.lot_size,
    }
    with factory.begin() as session:
        config = StrategyConfig(name='dual_ma', params_json=params)
        session.add(config)
        session.flush()
        task = BacktestTask(symbol=request.symbol, strategy_config_id=config.id,
                            data_batch_id=request.batch_id, initial_capital=request.initial_cash)
        session.add(task)
        session.flush()
        MarketDataRepository(session).add_signal_batch([
            BacktestSignal(task_id=task.id, symbol=row.symbol, signal_date=row.trade_date,
                           side=row.side, short_value=Decimal(str(row.sma_short)),
                           long_value=Decimal(str(row.sma_long)))
            for row in signals.itertuples(index=False)
        ])
        save_execution(session, task.id, result)
        task_id = task.id
    logger.info('回测执行记录提交成功 task_id=%d batch_id=%d', task_id, request.batch_id)
    return PipelineResult(task_id, request.batch_id, signals, result)
