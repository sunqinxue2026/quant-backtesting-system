"""第五阶段结果持久化；事务由调用方控制，不写第六阶段绩效。"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import BacktestTask, BacktestOrder, BacktestTrade, BacktestSnapshot
from .backtest import BacktestResult


def save_execution(session: Session, task_id: int, result: BacktestResult) -> None:
    """保存一次任务的执行明细；重复保存明确拒绝。"""
    task = session.get(BacktestTask, task_id)
    if task is None:
        raise ValueError("回测任务不存在")
    if not result.snapshots:
        raise ValueError("账户快照不能为空")
    if task.status == "completed":
        raise ValueError("任务执行结果已经保存")
    if session.scalar(select(BacktestSnapshot.id).where(BacktestSnapshot.task_id == task_id).limit(1)) is not None:
        raise ValueError("任务执行结果已经保存")
    order_ids: dict[int, int] = {}
    for order in result.orders:
        if order.symbol != task.symbol:
            raise ValueError("订单股票与任务不一致")
        row = BacktestOrder(task_id=task_id, signal_date=order.signal_date,
            execute_date=order.execute_date, side=order.side.value,
            quantity=max(0, order.quantity), status=order.status.value, reason=order.reason)
        session.add(row)
        session.flush()
        order_ids[order.order_id] = row.id
    for trade in result.trades:
        session.add(BacktestTrade(task_id=task_id, order_id=order_ids[trade.order_id],
            trade_date=trade.trade_date, side=trade.side.value, quantity=trade.quantity,
            price=trade.price, commission=trade.commission, tax=trade.tax))
    for snapshot in result.snapshots:
        session.add(BacktestSnapshot(task_id=task_id, trade_date=snapshot.trade_date,
            cash=snapshot.cash, position_quantity=snapshot.position_quantity,
            close_price=snapshot.close_price, total_value=snapshot.total_value,
            daily_return=snapshot.daily_return))
    task.status = "completed"
    session.flush()


def query_execution(session: Session, task_id: int) -> dict[str, list]:
    return {
        "orders": list(session.scalars(select(BacktestOrder).where(BacktestOrder.task_id == task_id).order_by(BacktestOrder.id))),
        "trades": list(session.scalars(select(BacktestTrade).where(BacktestTrade.task_id == task_id).order_by(BacktestTrade.trade_date, BacktestTrade.id))),
        "snapshots": list(session.scalars(select(BacktestSnapshot).where(BacktestSnapshot.task_id == task_id).order_by(BacktestSnapshot.trade_date))),
    }
