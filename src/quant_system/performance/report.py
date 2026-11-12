"""第五阶段持久化结果 -> 第六阶段绩效、报告和图表。"""
from pathlib import Path
from datetime import date
from decimal import Decimal
import json
import pandas as pd
from sqlalchemy import select
from ..database import BacktestTask, StrategyConfig, DataImportBatch, BacktestSignal, BacktestResult
from ..backtest_pipeline import BacktestRequest, load_batch_frame
from ..engine.persistence import query_execution
from ..indicators import add_indicators
from ..visualization import plot_report
from .analyzer import analyze_performance


def generate_report(factory, task_id, output_root, *, annualization_days=252, risk_free_rate=0.0):
    """分析已完成任务；拒绝覆盖已有绩效。文件失败不写绩效，提交失败保留已生成文件并抛错。"""
    with factory() as session:
        task = session.get(BacktestTask, task_id)
        if task is None or task.status != 'completed':
            raise ValueError('任务不存在或未完成')
        if session.scalar(select(BacktestResult.id).where(BacktestResult.task_id==task_id)) is not None:
            raise ValueError('任务绩效已保存，不自动覆盖')
        config = session.get(StrategyConfig,task.strategy_config_id)
        batch = session.get(DataImportBatch,task.data_batch_id)
        params = dict(config.params_json)
        request = BacktestRequest(batch.id,task.symbol,date.fromisoformat(params['start']),date.fromisoformat(params['end']),params['price_type'],task.initial_capital,params['short_window'],params['long_window'])
        prices = load_batch_frame(session,request)
        execution = query_execution(session,task_id)
        signals = pd.DataFrame([dict(signal_date=r.signal_date,side=r.side) for r in session.scalars(select(BacktestSignal).where(BacktestSignal.task_id==task_id))],columns=['signal_date','side'])
        metrics,curves = analyze_performance(execution['snapshots'],execution['trades'],task.initial_capital,annualization_days=annualization_days,risk_free_rate=risk_free_rate)
        if list(curves.trade_date.dt.date) != list(prices.trade_date):
            raise ValueError('快照与批次行情日期不完全对齐')
        if not all(abs(float(a)-float(b)) < 1e-8 for a,b in zip(curves.close,prices.close)):
            raise ValueError('快照与基准价格不一致')
        metadata = dict(task_id=task_id,batch_id=batch.id,symbol=task.symbol,source=batch.source,
            source_file=batch.source_file,is_synthetic=batch.is_synthetic,data_as_of=str(batch.data_as_of),
            dataset=batch.units_json,price_type=batch.price_type,parameters=params,
            initial_capital=str(task.initial_capital),start=str(curves.trade_date.iloc[0].date()),end=str(curves.trade_date.iloc[-1].date()),
            limitations='研究型历史模拟；未还原公司行动现金流；未建模完整停牌、涨跌停和真实撮合；合成数据不代表策略有效性')
    prices = add_indicators(prices,short_window=params['short_window'],long_window=params['long_window'])
    folder = Path(output_root) / f'task_{task_id}'
    folder.mkdir(parents=True,exist_ok=True)
    subtitle = f"{metadata['symbol']} | {metadata['start']}至{metadata['end']} | {metadata['price_type']} | SMA {params['short_window']}/{params['long_window']} | synthetic={metadata['is_synthetic']}"
    subtitle += '\n来源='+metadata['source']+' | 成本='+str(params.get('costs',{}))
    charts = plot_report(curves,prices,signals,folder,task_id,subtitle)
    payload = dict(metrics=metrics,metadata=metadata,files=charts+['curves.csv','report.json'])
    curves.to_csv(folder/'curves.csv',index=False)
    (folder/'report.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    with factory.begin() as session:
        session.add(BacktestResult(task_id=task_id,metrics_json=payload))
        session.flush()
    return payload
