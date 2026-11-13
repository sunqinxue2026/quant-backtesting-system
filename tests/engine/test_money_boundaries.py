"""本轮独立回归：所有金额边界均来自手算，不改动历史测试。"""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_UP, localcontext

import pandas as pd
import pytest
from sqlalchemy import func, select

from quant_system.backtest_pipeline import BacktestRequest, run_batch_backtest
from quant_system.database import (
    create_session_factory, DataImportBatch, StockDaily, StrategyConfig, BacktestTask,
    BacktestSignal, BacktestOrder, BacktestTrade, BacktestSnapshot,
)
from quant_system.engine import BacktestEngine, CostModel, Portfolio, Side
from quant_system.engine.backtest import MAX_ORDER_QUANTITY
from quant_system.engine.models import Order, OrderStatus
from quant_system.engine.persistence import save_execution, query_execution
from quant_system.money import normalize_initial_cash

D = Decimal
SYMBOL = '000001.SZ'
DAY = date(2024, 1, 2)
NEXT = date(2024, 1, 3)


def costs(minimum='0', tax='0', rate='0', slippage='0', lot=100):
    return CostModel(D(rate), D(minimum), D(tax), D(slippage), lot)


class Signals:
    def __init__(self, sides):
        self.sides = sides

    def generate_signals(self, data):
        return pd.DataFrame([
            dict(symbol=SYMBOL, trade_date=data.iloc[i].trade_date, side=side)
            for i, side in enumerate(self.sides)
        ], columns=['symbol', 'trade_date', 'side'])


def bars(price='0.01', periods=3):
    return pd.DataFrame(dict(symbol=[SYMBOL]*periods,
        trade_date=pd.date_range(DAY, periods=periods), open=[price]*periods,
        close=[price]*periods))


def auto(cash, price, model):
    engine = BacktestEngine(Signals(['BUY']), D(cash), model)
    estimate_account = Portfolio(D(cash), model)
    result = engine.run(bars(price, 2))
    return engine, estimate_account, result


@pytest.mark.parametrize('cash,price,model,quantity,remaining', [
    ('1000.00', '10.000001', costs(), 100, '0.00'),
    ('999.99', '10.000001', costs(), 0, '999.99'),
    ('2000.00', '10.000001', costs(), 200, '0.00'),
    ('1999.99', '10.000001', costs(), 100, '999.99'),
    ('2005.00', '10.000001', costs(minimum='5'), 200, '0.00'),
    ('2004.99', '10.000001', costs(minimum='5'), 100, '999.99'),
    ('2025.00', '10', costs(minimum='5', slippage='100'), 200, '0.00'),
    ('2024.99', '10', costs(minimum='5', slippage='100'), 100, '1009.99'),
    ('2002.00', '10', costs(rate='.001'), 200, '0.00'),
])
def test_auto_maximum_matches_manual_and_estimate(cash, price, model, quantity, remaining):
    engine, account, result = auto(cash, price, model)
    order = result.orders[0]
    assert order.quantity == quantity
    assert result.final_cash == D(remaining)
    assert result.final_position == quantity
    assert order.status is (OrderStatus.FILLED if quantity else OrderStatus.REJECTED)
    if quantity:
        estimate = account.estimate(Side.BUY, quantity, D(price))
        trade = result.trades[0]
        assert (trade.quantity, trade.price, trade.commission, trade.tax) == (
            quantity, estimate.execution_price, estimate.commission, estimate.tax)
        assert result.final_cash == account.cash + estimate.total_cash_change
        assert engine.portfolio.trades == result.trades
    else:
        assert not result.trades
    assert account.cash + account.estimate(Side.BUY, quantity + model.lot_size, D(price)).total_cash_change < 0


def test_auto_expansion_passes_rounding_plateau():
    # 0.000001 * 5000 = 0.005 -> 0.00; 15000 = 0.015 -> 0.02.
    _, account, result = auto('.01', '.000001', costs())
    assert result.orders[0].quantity == 14900
    assert result.final_cash == 0
    assert account.estimate(Side.BUY, 15000, D('.000001')).total_cash_change == D('-.02')


@pytest.mark.parametrize('lot', [1, 100, MAX_ORDER_QUANTITY+1])
def test_auto_search_stops_at_storage_limit(lot, monkeypatch):
    count = 0
    actual = Portfolio.estimate

    def counted(self, *args, **kwargs):
        nonlocal count
        count += 1
        assert count < 70, 'bounded search must terminate'
        return actual(self, *args, **kwargs)

    monkeypatch.setattr(Portfolio, 'estimate', counted)
    _, _, result = auto('10000000', '.000001', costs(lot=lot))
    expected = MAX_ORDER_QUANTITY // lot * lot
    assert result.orders[0].quantity == expected
    assert result.final_position == expected
    assert result.orders[0].status is (OrderStatus.FILLED if expected else OrderStatus.REJECTED)


@pytest.mark.parametrize('price', ['0', '-1', 'NaN', 'Infinity'])
def test_auto_invalid_price_rejected_without_state_change(price):
    engine = BacktestEngine(Signals([]), D('1000'), costs())
    before = deepcopy(engine.portfolio.__dict__)
    order = Order(1, SYMBOL, DAY, NEXT, Side.BUY, -1)
    filled, trade = engine._execute(order, D(price), NEXT)
    assert filled.status is OrderStatus.REJECTED and trade is None
    assert engine.portfolio.__dict__ == before


@pytest.mark.parametrize('cash,tax,allowed,remaining', [
    ('6', '0', False, '0'),
    ('10', '0', True, '0'),
    ('9.99', '0', False, '3.99'),
    ('10.01', '.01', True, '0'),
    ('10', '.01', False, '4'),
])
def test_sell_cash_guard_is_atomic_and_allows_cash_topup(cash, tax, allowed, remaining):
    account = Portfolio(D(cash), costs(minimum='5', tax=tax))
    account.settle_trade(SYMBOL, Side.BUY, 100, D('.01'), DAY, 1, 1)
    account.make_bought_sellable(NEXT)
    before = deepcopy(account.__dict__)
    if not allowed:
        with pytest.raises(ValueError, match='资金不足'):
            account.settle_trade(SYMBOL, Side.SELL, 100, D('.01'), NEXT, 2, 2)
        assert account.__dict__ == before
    else:
        trade = account.settle_trade(SYMBOL, Side.SELL, 100, D('.01'), NEXT, 2, 2)
        assert trade.commission == 5
        assert trade.tax == (D('.01') if tax == '.01' else 0)
        assert account.position(SYMBOL).quantity == account.position(SYMBOL).sellable_quantity == 0
        assert len(account.trades) == 2
    assert account.cash == D(remaining)


def test_rejected_order_does_not_create_empty_position():
    account = Portfolio(D('1'), costs())
    before = deepcopy(account.__dict__)
    with pytest.raises(ValueError):
        account.settle_trade(SYMBOL, Side.BUY, 100, D('1'), DAY, 1, 1)
    assert account.__dict__ == before


@pytest.mark.parametrize('raw,expected', [('1.005', '1.00'), ('1.015', '1.02'), ('10000.999', '10001.00')])
def test_initial_cash_is_explicit_half_even(raw, expected):
    with localcontext() as context:
        context.rounding = ROUND_UP
        engine = BacktestEngine(Signals([]), D(raw), costs())
        result = engine.run(bars('1'))
    assert normalize_initial_cash(D(raw)) == D(expected)
    assert engine.initial_cash == engine.portfolio.initial_cash == D(expected)
    assert all(s.cash == s.total_value == D(expected) for s in result.snapshots)


@pytest.mark.parametrize('raw', ['0.001', '0', '-1', 'NaN', 'Infinity'])
def test_initial_cash_invalid_after_normalization(raw):
    with pytest.raises(ValueError):
        Portfolio(D(raw))
    with pytest.raises(ValueError):
        BacktestEngine(Signals([]), D(raw))


@pytest.mark.parametrize('minimum,expected', [('5.005', '5.00'), ('5.015', '5.02')])
def test_minimum_commission_rounding_preserves_ratio_precision(minimum, expected):
    model = costs(minimum=minimum, rate='.000312345', tax='.00056789', slippage='5.123456')
    assert model.minimum_commission == D(expected)
    assert (model.commission_rate, model.stamp_tax_rate, model.slippage_bps) == (
        D('.000312345'), D('.00056789'), D('5.123456'))
    account = Portfolio(D('100'), model)
    estimate = account.estimate(Side.BUY, 100, D('.01'))
    trade = account.settle_trade(SYMBOL, Side.BUY, 100, D('.01'), DAY, 1, 1)
    assert trade.commission == D(expected)
    assert account.cash == D('100') + estimate.total_cash_change
    assert account.cash.as_tuple().exponent == -2


@pytest.fixture
def database(tmp_path):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'boundaries.db'}")
    values = [10, 9, 8, 9, 10, 11, 10, 9, 8]
    dates = pd.bdate_range('2024-01-02', periods=len(values)).date
    with factory.begin() as session:
        batch = DataImportBatch(source='synthetic/test', source_file='manual', price_type='未复权',
            units_json={'price': 'CNY', 'volume': '股', 'amount': 'CNY'},
            is_synthetic=True, accepted_rows=len(values))
        session.add(batch)
        session.flush()
        batch_id = batch.id
        for day, value in zip(dates, values):
            session.add(StockDaily(symbol=SYMBOL, trade_date=day, open=value, high=value+1,
                low=value-1, close=value, volume=100, amount=value*100,
                source='synthetic/test', price_type='未复权', import_batch_id=batch_id))
    request = BacktestRequest(batch_id, SYMBOL, dates[0], dates[-1], '未复权', order_quantity=0)
    yield factory, request
    factory.kw['bind'].dispose()


@pytest.mark.parametrize('raw,expected', [('1.005', '1.00'), ('1.015', '1.02')])
def test_sqlite_capital_snapshots_and_performance_denominator(database, tmp_path, monkeypatch, raw, expected):
    from quant_system.performance import report
    factory, request = database
    result = run_batch_backtest(replace(request, initial_cash=D(raw)), factory, costs())
    with factory() as session:
        task = session.get(BacktestTask, result.task_id)
        saved = query_execution(session, result.task_id)
        assert task.initial_capital == D(expected)
        assert [s.cash for s in saved['snapshots']] == [s.cash for s in result.execution.snapshots]
        assert all(s.cash == s.total_value == task.initial_capital for s in saved['snapshots'])
    actual = report.analyze_performance
    received = []

    def analyze(snapshots, trades, initial_capital, **kwargs):
        received.append(initial_capital)
        return actual(snapshots, trades, initial_capital, **kwargs)

    monkeypatch.setattr(report, 'analyze_performance', analyze)
    monkeypatch.setattr(report, 'plot_report', lambda *args, **kwargs: [])
    payload = report.generate_report(factory, result.task_id, tmp_path / 'reports')
    assert received == [D(expected)]
    assert D(payload['metadata']['initial_capital']) == D(expected)
    assert payload['metrics']['total_return'] == 0


def test_sqlite_zero_normalized_capital_creates_no_task(database):
    factory, request = database
    with pytest.raises(ValueError, match='大于零'):
        run_batch_backtest(replace(request, initial_cash=D('.001')), factory, costs())
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BacktestTask)) == 0
        assert session.scalar(select(func.count()).select_from(StrategyConfig)) == 0


@pytest.mark.parametrize('initial,expected_status,final_cash,position', [
    ('6', 'REJECTED', '0', 100), ('10', 'FILLED', '0', 0), ('9.99', 'REJECTED', '3.99', 100),
])
def test_sqlite_sell_order_trade_cash_and_position_match(database, initial, expected_status, final_cash, position):
    factory, request = database
    model = costs(minimum='5.005')
    result = BacktestEngine(Signals(['BUY', 'SELL']), D(initial), model, 100).run(bars())
    with factory.begin() as session:
        config = StrategyConfig(name='manual', params_json={})
        session.add(config)
        session.flush()
        task = BacktestTask(symbol=SYMBOL, strategy_config_id=config.id,
            data_batch_id=request.batch_id, initial_capital=D(initial))
        session.add(task)
        session.flush()
        task_id = task.id
        save_execution(session, task_id, result)
    with factory() as session:
        saved = query_execution(session, task_id)
        assert saved['orders'][-1].status == expected_status
        assert len(saved['trades']) == (2 if expected_status == 'FILLED' else 1)
        by_id = {o.id: o for o in saved['orders']}
        for stored, memory in zip(saved['trades'], result.trades):
            assert by_id[stored.order_id].status == 'FILLED'
            assert by_id[stored.order_id].quantity == stored.quantity == memory.quantity
            assert (stored.price, stored.commission, stored.tax) == (memory.price, memory.commission, memory.tax)
        for stored, memory in zip(saved['snapshots'], result.snapshots):
            assert (stored.cash, stored.position_quantity, stored.total_value) == (
                memory.cash, memory.position_quantity, memory.total_value)
        assert saved['snapshots'][-1].cash == result.final_cash == D(final_cash)
        assert saved['snapshots'][-1].position_quantity == result.final_position == position


def test_sqlite_partial_flush_failure_rolls_back_without_mutating_result(database, monkeypatch):
    import quant_system.backtest_pipeline as pipeline
    factory, request = database
    request = replace(request, initial_cash=D('10000.015'), order_quantity=100)
    actual = pipeline.save_execution
    captured = []

    def fail(session, task_id, result):
        before = deepcopy(result)
        actual(session, task_id, result)
        captured.append((result, before))
        raise RuntimeError('forced failure after execution flush')

    monkeypatch.setattr(pipeline, 'save_execution', fail)
    with pytest.raises(RuntimeError, match='forced failure'):
        run_batch_backtest(request, factory, costs())
    assert len(captured) == 1 and captured[0][0] == captured[0][1]
    with factory() as session:
        for model in (StrategyConfig, BacktestTask, BacktestSignal, BacktestOrder, BacktestTrade, BacktestSnapshot):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(func.count()).select_from(DataImportBatch)) == 1
        assert session.scalar(select(func.count()).select_from(StockDaily)) == 9


@pytest.mark.parametrize('model', [
    costs(), costs(minimum='5.005', rate='.001'),
    costs(minimum='5.015', rate='.000312345', slippage='5.123456'),
])
@pytest.mark.parametrize('price', ['.000001', '.00005', '.01', '10.000001'])
def test_estimate_is_pure_deterministic_and_buy_affordability_monotone(model, price):
    account = Portfolio(D('1000'), model)
    before = deepcopy(account.__dict__)
    quantities = [n * model.lot_size for n in range(1, 201)] + [MAX_ORDER_QUANTITY // model.lot_size * model.lot_size]
    estimates = [account.estimate(Side.BUY, n, D(price)) for n in quantities]
    assert estimates == [account.estimate(Side.BUY, n, D(price)) for n in quantities]
    assert account.__dict__ == before
    outflows = [-e.total_cash_change for e in estimates]
    assert outflows == sorted(outflows)
    affordable = [value <= account.cash for value in outflows]
    assert affordable == sorted(affordable, reverse=True)


def test_sqlite_auto_rounded_fill_matches_order_trade_and_snapshot(database):
    factory, request = database
    _, _, result = auto('1000', '10.000001', costs())
    with factory.begin() as session:
        config = StrategyConfig(name='manual-auto', params_json={})
        session.add(config)
        session.flush()
        task = BacktestTask(symbol=SYMBOL, strategy_config_id=config.id,
            data_batch_id=request.batch_id, initial_capital=D('1000.00'))
        session.add(task)
        session.flush()
        task_id = task.id
        save_execution(session, task_id, result)
    with factory() as session:
        saved = query_execution(session, task_id)
        assert len(saved['orders']) == len(saved['trades']) == 1
        order, trade = saved['orders'][0], saved['trades'][0]
        assert order.status == 'FILLED'
        assert order.quantity == trade.quantity == 100
        assert trade.order_id == order.id
        assert (trade.price, trade.commission, trade.tax) == (D('10.000001'), 0, 0)
        assert saved['snapshots'][0].cash == D('1000.00')
        assert saved['snapshots'][-1].cash == result.final_cash == D('0.00')
        assert saved['snapshots'][-1].position_quantity == result.final_position == 100


@pytest.mark.parametrize('precision', [2, 6, 28])
@pytest.mark.parametrize('rounding', ['ROUND_UP', 'ROUND_DOWN'])
@pytest.mark.parametrize('raw,expected', [
    ('1.005', '1.00'), ('1.015', '1.02'), ('0.001', '0.00'),
    ('1234567890123456.785', '1234567890123456.78'),
    ('9999999999999999.995', '10000000000000000.00'),
])
def test_money_normalization_independent_of_context(precision, rounding, raw, expected):
    from quant_system.money import normalize_money
    with localcontext() as context:
        context.prec = precision
        context.rounding = rounding
        assert normalize_money(D(raw)) == D(expected)
        assert context.prec == precision and context.rounding == rounding


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('failure', ['average_cost', 'trade_construction'])
def test_settlement_precommit_failure_preserves_complete_account(existing, failure, monkeypatch):
    from decimal import InvalidOperation
    import quant_system.engine.portfolio as module
    account = Portfolio(D('1000'), costs())
    held = account.position(SYMBOL) if existing else None
    before = deepcopy(account.__dict__)
    if failure == 'trade_construction':
        def fail(*args, **kwargs):
            raise RuntimeError('forced trade construction failure')
        monkeypatch.setattr(module, 'Trade', fail)
        with pytest.raises(RuntimeError, match='forced trade'):
            account.settle_trade(SYMBOL, Side.BUY, 100, D('.01'), DAY, 1, 1)
    else:
        # estimate/turnover fit prec=6; average cost 0.010000 requires >6 digits
        # use price 1 so average cost 1.000000 requires 7 digits.
        with localcontext() as context:
            context.prec = 6
            with pytest.raises(InvalidOperation):
                account.settle_trade(SYMBOL, Side.BUY, 100, D('1'), DAY, 1, 1)
    assert account.__dict__ == before
    if existing:
        assert account.positions[SYMBOL] is held


def test_successful_settlement_preserves_position_reference():
    account = Portfolio(D('1000'), costs())
    held = account.position(SYMBOL)
    account.settle_trade(SYMBOL, Side.BUY, 100, D('1'), DAY, 1, 1)
    assert account.positions[SYMBOL] is held
    assert held.quantity == 100 and held.average_cost == D('1')


def test_quantity_columns_use_portable_signed_integer():
    from sqlalchemy import Integer
    from sqlalchemy.dialects import mysql, sqlite
    for model, field in [(BacktestOrder, 'quantity'), (BacktestTrade, 'quantity'),
                         (BacktestSnapshot, 'position_quantity')]:
        column = model.__table__.c[field]
        assert type(column.type) is Integer
        assert column.type.compile(dialect=mysql.dialect()) == 'INTEGER'
        assert column.type.compile(dialect=sqlite.dialect()) == 'INTEGER'
    assert MAX_ORDER_QUANTITY == 2**31 - 1


@pytest.mark.parametrize('order_quantity,allowed', [
    (MAX_ORDER_QUANTITY, True),
    (MAX_ORDER_QUANTITY + 1, False),
    (-1, False),
    (True, False),
    (1.5, False),
    (None, True),
])
def test_manual_order_quantity_respects_storage_limit(order_quantity, allowed):
    if allowed:
        engine = BacktestEngine(Signals([]), D('1000'), costs(), order_quantity)
        assert engine.order_quantity == order_quantity
    else:
        with pytest.raises(ValueError, match='订单数量'):
            BacktestEngine(Signals([]), D('1000'), costs(), order_quantity)


def test_direct_settlement_rejects_quantity_above_storage_limit_without_state_change():
    account = Portfolio(D('1000000'), costs())
    before = deepcopy(account.__dict__)
    with pytest.raises(ValueError, match='MAX_ORDER_QUANTITY'):
        account.settle_trade(
            SYMBOL, Side.BUY, MAX_ORDER_QUANTITY + 1, D('.01'), DAY, 1, 1
        )
    assert account.__dict__ == before
