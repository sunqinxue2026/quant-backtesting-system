"""第八阶段本机研究演示界面。运行：python -m streamlit run web_app.py"""
from pathlib import Path
from datetime import date
from decimal import Decimal
import json
import os
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
import pandas as pd
import streamlit as st
from sqlalchemy import select
from quant_system.database import (create_session_factory, DataImportBatch, StockDaily,
    BacktestTask, StrategyConfig, BacktestSignal, BacktestOrder, BacktestTrade,
    BacktestSnapshot, BacktestResult)
from quant_system.data import DataLoadRequest, CsvMarketDataSource
from quant_system.cleaning.cleaner import MarketDataCleaner
from quant_system.data_import import import_csv
from quant_system.backtest_pipeline import BacktestRequest, run_batch_backtest
from quant_system.engine import CostModel
from quant_system.performance import generate_report
from quant_system.indicators import add_indicators

st.set_page_config(page_title='量化研究工作台', page_icon='📈', layout='wide')
st.markdown('''<style>
.stApp {background:#f5f7fb;color:#142b4a;color-scheme:light;}
[data-testid="stSidebar"] {background:#10213b;color:#eef4ff;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {color:#eef4ff;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#c5d2e6;}
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background:#ffffff;color:#142b4a;border-color:#9aacc4;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] input {
    color:#142b4a;-webkit-text-fill-color:#142b4a;
}
[data-testid="stSidebar"] [data-baseweb="select"] svg {fill:#142b4a;color:#142b4a;}
[data-baseweb="popover"] [role="listbox"] {background:#ffffff;color:#142b4a;}
[data-baseweb="popover"] [role="option"] {color:#142b4a;}
[data-testid="stMetric"] {background:white;color:#142b4a;padding:18px;border-radius:14px;border:1px solid #e4eaf3;}
h1,h2,h3 {color:#142b4a;}
/* Leave room for Streamlit's fixed header so the environment caption stays visible. */
[data-testid="stMainBlockContainer"], .main .block-container {padding-top:5rem;}
@media (max-width:640px) {
    [data-testid="stMainBlockContainer"], .main .block-container {padding-top:4.5rem;}
}
</style>''', unsafe_allow_html=True)

@st.cache_resource
def connect(url):
    return create_session_factory(url)

def table(model, session, *conditions):
    rows = session.scalars(select(model).where(*conditions).order_by(model.id)).all()
    return pd.DataFrame([{c.name: getattr(row,c.name) for c in model.__table__.columns} for row in rows])

def display(frame):
    out = frame.copy()
    for col in out.columns:
        out[col] = out[col].map(lambda v: float(v) if isinstance(v,Decimal) else v)
    st.dataframe(out, use_container_width=True, hide_index=True)

def percent(value):
    return '未定义' if value is None else f'{value:.2%}'

with st.sidebar:
    st.title('量化研究工作台')
    st.caption('从行情到策略 · 每一步可追溯')
    mode = st.selectbox('数据环境', ['第七阶段手动演示库','独立网页数据库','环境变量数据库'])
    page = st.radio('功能导航', ['系统总览','数据管理','创建回测','任务与逐日回放','绩效与任务对比','使用教程'])
    st.divider()
    st.caption('研究型历史模拟 · 单股票 · 只做多\n信号日与成交日分离；不执行真实交易。')
if page == '使用教程':
    st.title('使用教程')
    st.write('从已有任务开始：确认数据 → 回放交易 → 阅读绩效 → 修改参数 → 对比结果。')
    tutorial_pdf = ROOT / 'docs' / '量化研究工作台_使用教程.pdf'
    if tutorial_pdf.exists():
        st.download_button('下载完整使用教程 PDF', tutorial_pdf.read_bytes(),
                           '量化研究工作台_使用教程.pdf', 'application/pdf')
    else:
        st.info('PDF 暂不可用，仍可阅读下方完整操作说明。')
    basics, replay, report_help, experiment = st.tabs(['快速上手','逐日回放','报告怎么看','创建与对比'])
    with basics:
        st.markdown("""
### 第一次使用
1. 左侧数据环境选择“第七阶段手动演示库”。数据库不同，任务编号不能混用。
2. 进入“系统总览”，查看批次、任务、绩效和行情数量。
3. 进入“数据管理 → 已有批次”，确认股票、日期、来源、价格口径和单位。
4. 使用已有批次即可回测，不需要重复上传相同行情。
5. 进入“任务与逐日回放”，选择已有任务，再阅读“绩效与任务对比”。

### 数据怎样进入系统
标准 CSV 包含 symbol、trade_date、open、high、low、close、volume、amount 八列。
价格和成交额单位为人民币元，成交量为股；页面不会自动进行单位换算。
上传时填写来源、数据截至日期、价格口径，并如实标记是否为合成数据。
先查看合格、待复核、拒绝记录，再主动点击导入；只有 accepted 行情入库。

**批次是一份行情输入；任务是一组参数的运行；绩效是对任务结果的分析。**
""")
    with replay:
        st.markdown("""
### 对照一笔买卖
1. 选择任务，展开“全部订单”，找到一条 BUY。
2. 记下 signal_date（信号日）和 execute_date（执行日）。
3. 拖动“选择交易日”到信号日，查看当日收盘信号。
4. 切到执行日，查看当日成交，以及现金和持仓变化。
5. 再查看卖出日和期末账户。

收盘后产生信号，下一行情日开盘尝试执行。资金不足可能拒单；信号不等于成交。
现金、持仓、收盘价与总资产随日期变化；价格均线图目前展示完整区间，不随滑块截断。
可卖数量和平均成本未存入快照，页面不会猜测展示。

**总资产 = 现金 + 持仓数量 × 当日收盘价。**

已有任务的期末示例：98474.98 + 100 × 11.70 = 99644.98 元。
""")
    with report_help:
        st.markdown("""
### 按什么顺序阅读
先看最终资产和总收益，再看回撤，随后看交易统计，最后看基准与参数。
以下是已有 SMA5/20、10万元初始资金、每次100股任务的示例，不是所有新任务的固定结果。

| 指标 | 示例 | 含义 |
|---|---:|---|
| 最终资产 | 99644.98元 | 现金与期末持仓市值之和 |
| 总收益率 | -0.35502% | 最终资产/初始资金-1 |
| 最大回撤 | -0.3925% | 相对包含初始资金的历史峰值的最大跌幅 |
| 成交笔数 | 33 | 买入、卖出各计一笔 |
| 完整平仓/未平仓 | 16/1 | 未平仓不计完整交易胜率 |
| 胜率 | 25% | 16次完整交易中4次盈利 |
| 已实现净盈亏 | -356.44元 | 完整交易盈亏，不等于全部账户资产变化 |

年化收益按自然日区间折算；波动率按252日年化；夏普衡量风险调整后收益。
空值代表统计条件不满足，查看报告 notes，不能随意当成0。

### 四类图与报告
- 净值：以初始资金为1，观察账户变化。
- 回撤：观察从历史资产高点回落的深度，负值越低回撤越大。
- 价格、均线与信号：解释交叉；标记是信号日，不是成交日。
- 策略与基准：比较曲线，但固定100股策略与满仓无成本价格基准仓位不同。

在“完整报告”查看 metrics（指标）、metadata（来源与参数）和 metrics.definitions（公式口径）。
通过“下载绩效报告 JSON”保留报告。

未还原分红送转，未完整建模停牌、涨跌停和实际撮合；结果不能证明投资有效性。
""")
    with experiment:
        st.markdown("""
### 创建一个可解释的对照实验
1. 进入“创建回测”，选择已有批次、股票和日期区间。
2. 设置初始资金、100股整数倍买入数量和短长均线；短周期必须小于长周期。
3. 核对佣金率、最低佣金、卖出税率和滑点。5个基点等于0.05%。
4. 点击“运行回测并生成报告”，等待完成并记下任务编号。
5. 进入“绩效与任务对比”，选择原任务和新任务。

建议只把5/20日改为10/30日，其他条件不变，解释交易次数和结果的变化。
主动再次提交会创建新任务；普通刷新不自动重跑。不要连续点击提交。
若执行已提交但报告失败，保留任务编号，到绩效页重试生成；已保存绩效不会自动覆盖。

### 五分钟演示顺序
数据来源 → 均线参数 → 一次信号和次日成交 → 现金与持仓 → 绩效与限制 → 参数对比。
SQLite 用于轻量演示；环境变量数据库的类型取决于连接配置。切换环境前确认数据身份。
""")
    st.stop()

if mode == '环境变量数据库':
    url = os.getenv('DATABASE_URL')
    if not url:
        st.info('当前进程未配置 DATABASE_URL。请先使用 SQLite 环境，或在启动配置中设置连接。')
        st.stop()
else:
    db = Path(os.getenv('QUANT_WEB_DEMO_DB', str(ROOT / 'reports/stage7/manual_sqlite/demo.db'))) if mode == '第七阶段手动演示库' else ROOT / 'reports/web/web.db'
    db.parent.mkdir(parents=True, exist_ok=True)
    url = f'sqlite:///{db.as_posix()}'
try:
    factory = connect(url)
    with factory() as s:
        batches = table(DataImportBatch,s)
        tasks = table(BacktestTask,s)
        reports = table(BacktestResult,s)
except Exception:
    st.error('数据库连接失败。请检查环境配置；页面不会显示连接串或密码。')
    st.stop()
st.caption(f'当前环境：{mode} ｜ {factory.kw["bind"].dialect.name} ｜ 新回测会写入此环境')

if page == '系统总览':
    st.title('让每一笔模拟交易，都讲得清楚')
    st.write('选择行情、配置双均线、观察逐日执行，再用账户曲线解释结果。')
    cols=st.columns(4)
    for col,label,value in zip(cols,['数据批次','回测任务','已保存绩效','行情记录'],[len(batches),len(tasks),len(reports),int(batches.accepted_rows.sum()) if not batches.empty else 0]):
        col.metric(label,value)
    st.subheader('系统运行链路')
    st.info('① CSV 读取与清洗 → ② 行情与来源入库 → ③ 指标和信号 → ④ 次日开盘执行 → ⑤ 账户快照 → ⑥ 绩效与图表')
    st.subheader('最近任务')
    display(tasks.tail(10).iloc[::-1])
    st.warning('固定100股策略与满仓价格基准仓位不同。未还原分红送转、完整停牌和涨跌停撮合；结果不能证明投资有效性。')

elif page == '数据管理':
    st.title('数据管理')
    browse,upload=st.tabs(['已有批次','上传与清洗'])
    with browse:
        if batches.empty:
            st.info('当前环境暂无批次，请上传 CSV。')
        else:
            bid=st.selectbox('行情批次',batches.id.tolist()[::-1])
            row=batches[batches.id==bid].iloc[0]
            st.write(f'来源：{row.source} ｜ 口径：{row.price_type} ｜ 合成数据：{row.is_synthetic}')
            with factory() as s:
                prices=table(StockDaily,s,StockDaily.import_batch_id==int(bid))
            display(prices)
            st.json(row.units_json)
    with upload:
        st.write('标准8列：symbol、trade_date、open、high、low、close、volume、amount。单位须为元、股、元，页面不自动换算。')
        file=st.file_uploader('选择行情 CSV',type=['csv'])
        source=st.text_input('真实数据来源（合成数据请说明）')
        c1,c2,c3=st.columns(3)
        asof=c1.date_input('数据截至日期',date.today())
        price_type=c2.selectbox('价格口径',['未复权','前复权','后复权'])
        synthetic=c3.checkbox('这是合成测试数据',False)
        if file is not None:
            import hashlib
            digest=hashlib.sha256(file.getvalue()).hexdigest()
            folder=ROOT/'reports/web/uploads'/digest
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/Path(file.name).name
            path.write_bytes(file.getvalue())
            request=DataLoadRequest(path,source,str(asof),price_type,{'price':'CNY','volume':'股','amount':'CNY'},synthetic)
            try:
                clean=MarketDataCleaner().clean(CsvMarketDataSource().load(request))
                st.json(clean.report.to_dict())
                for name,frame in [('合格',clean.accepted),('待复核',clean.review),('拒绝',clean.rejected)]:
                    with st.expander(f'{name}：{len(frame)} 行',expanded=name=='合格'):
                        display(frame)
                if st.button('将 accepted 行情导入当前数据库',disabled=not source.strip()):
                    prior=st.session_state.get('imported_files',set())
                    token=(mode,digest,source,str(asof),price_type,synthetic)
                    if token in prior:
                        st.warning('本会话已经导入该文件，请使用已有批次。')
                    else:
                        try:
                            result=import_csv(request,factory)
                            st.session_state['imported_files']=prior|{token}
                            st.success(f'已提交批次 {result.batch_id}，入库 {result.inserted_rows} 行。切换到创建回测即可使用。')
                        except Exception:
                            st.error('导入未成功，可能存在重复行情或字段约束冲突。没有覆盖原数据，请检查已有批次。')
            except Exception:
                st.error('CSV 无法读取或缺少必需字段，请使用标准8列表头及 UTF-8 编码。')

elif page == '创建回测':
    st.title('创建回测')
    if batches.empty:
        st.info('请先导入行情。'); st.stop()
    bid=st.selectbox('使用批次',batches[batches.accepted_rows>0].id.tolist()[::-1])
    if bid is None: st.stop()
    batch=batches[batches.id==bid].iloc[0]
    with factory() as s:
        prices=table(StockDaily,s,StockDaily.import_batch_id==int(bid))
    symbol=st.selectbox('股票',sorted(prices.symbol.unique()))
    prices=prices[prices.symbol==symbol]
    with st.form('run'):
        a,b,c=st.columns(3)
        start=a.date_input('开始日期',min(prices.trade_date))
        end=b.date_input('结束日期',max(prices.trade_date))
        cash=c.number_input('初始资金（元）',min_value=100.0,value=100000.0,step=1000.0)
        a,b,c=st.columns(3)
        short=a.number_input('短均线周期',1,1000,5)
        long=b.number_input('长均线周期',2,2000,20)
        quantity=c.number_input('买入数量（100股整手）',100,1000000,100,step=100)
        a,b,c,d=st.columns(4)
        commission=a.number_input('佣金率',0.0,1.0,0.0003,format='%.5f')
        minimum=b.number_input('最低佣金（元）',0.0,10000.0,5.0)
        tax=c.number_input('卖出税率',0.0,1.0,0.0005,format='%.5f')
        slip=d.number_input('滑点（基点）',0.0,9999.0,5.0)
        st.caption('信号在收盘后产生，下一行情日开盘执行。再次提交相同参数将有意创建新任务。')
        submitted=st.form_submit_button('运行回测并生成报告',type='primary')
    if submitted:
        if short>=long or start>end or quantity%100:
            st.error('请检查：短周期小于长周期、日期顺序正确、数量为100股整数倍。')
        else:
            task_id=None
            try:
                with st.status('正在执行回测',expanded=True) as status:
                    st.write('读取指定批次，计算指标和交叉信号。')
                    result=run_batch_backtest(BacktestRequest(int(bid),symbol,start,end,batch.price_type,Decimal(str(cash)),int(short),int(long),int(quantity)),factory,CostModel(commission,minimum,tax,slip))
                    task_id=result.task_id
                    st.write(f'任务 {task_id} 执行记录已提交，生成绩效和图表。')
                    generate_report(factory,task_id,ROOT/'reports/web'/uuid4().hex)
                    status.update(label=f'任务 {task_id} 完成',state='complete')
                st.success(f'任务 {task_id} 已保存。请到「任务与逐日回放」和「绩效与任务对比」查看。')
            except Exception:
                st.error(f'报告未完成；任务 {task_id} 的执行记录已保留，可在绩效页重试生成。' if task_id else '回测未完成，请检查行情日期、批次单位和参数。')

elif page == '任务与逐日回放':
    st.title('任务与逐日回放')
    if tasks.empty: st.info('暂无回测任务。'); st.stop()
    tid=st.selectbox('回测任务',tasks.id.tolist()[::-1])
    with factory() as s:
        snapshots=table(BacktestSnapshot,s,BacktestSnapshot.task_id==int(tid))
        signals=table(BacktestSignal,s,BacktestSignal.task_id==int(tid))
        orders=table(BacktestOrder,s,BacktestOrder.task_id==int(tid))
        trades=table(BacktestTrade,s,BacktestTrade.task_id==int(tid))
        task=s.get(BacktestTask,int(tid)); config=s.get(StrategyConfig,task.strategy_config_id)
        prices=table(StockDaily,s,
            StockDaily.import_batch_id==task.data_batch_id,
            StockDaily.symbol==task.symbol,
            StockDaily.price_type==config.params_json['price_type'],
            StockDaily.trade_date>=date.fromisoformat(config.params_json['start']),
            StockDaily.trade_date<=date.fromisoformat(config.params_json['end']))
    st.write(f'股票 {task.symbol} ｜ 批次 {task.data_batch_id} ｜ {task.status}')
    if not snapshots.empty:
        snapshots=snapshots.sort_values('trade_date')
        selected=st.select_slider('选择交易日',options=snapshots.trade_date.tolist(),value=snapshots.trade_date.iloc[-1])
        row=snapshots[snapshots.trade_date==selected].iloc[0]
        cols=st.columns(4)
        for col,label,value in zip(cols,['现金（元）','持仓（股）','收盘价（元）','总资产（元）'],[f'{row.cash:,.2f}',int(row.position_quantity),f'{row.close_price:.2f}',f'{row.total_value:,.2f}']): col.metric(label,value)
        indicator=add_indicators(prices,short_window=config.params_json['short_window'],long_window=config.params_json['long_window'])
        st.subheader('价格与均线')
        st.line_chart(indicator.set_index('trade_date')[['close','sma_short','sma_long']].astype(float))
        a,b=st.columns(2)
        with a:
            st.subheader('当日收盘信号'); display(signals[signals.signal_date==selected] if not signals.empty else signals)
        with b:
            st.subheader('当日成交'); display(trades[trades.trade_date==selected] if not trades.empty else trades)
        st.caption('当日信号不代表当日成交。可卖数量与平均成本未存入每日快照，页面不猜测其值。')
    for name,frame in [('全部信号',signals),('全部订单',orders),('全部成交',trades),('账户快照',snapshots)]:
        with st.expander(name): display(frame)

else:
    st.title('绩效与任务对比')
    if tasks.empty: st.info('暂无任务。'); st.stop()
    tid=st.selectbox('查看任务',tasks.id.tolist()[::-1])
    selected=reports[reports.task_id==tid] if not reports.empty else pd.DataFrame()
    if selected.empty:
        st.info('该任务尚未保存绩效。')
        if st.button('为该任务生成绩效报告'):
            try:
                with st.spinner('生成报告中'):
                    generate_report(factory,int(tid),ROOT/'reports/web'/uuid4().hex)
                st.rerun()
            except Exception:
                st.error('报告未完成，请检查任务是否 completed、快照与行情是否完整；数据库已有报告不会覆盖。')
    else:
        payload=selected.iloc[0].metrics_json; m=payload['metrics']
        cols=st.columns(4)
        for col,label,value in zip(cols,['最终资产（元）','总收益率','最大回撤','夏普比率'],[f"{m['final_equity']:,.2f}",percent(m['total_return']),percent(m['max_drawdown']),'未定义' if m['sharpe_ratio'] is None else f"{m['sharpe_ratio']:.3f}"]): col.metric(label,value)
        st.caption('最大回撤以负数表示；未定义统计保留为空。基准仓位与固定股数策略不同，不能直接认定超额收益。')
        with factory() as s: snap=table(BacktestSnapshot,s,BacktestSnapshot.task_id==int(tid))
        equity=snap.sort_values('trade_date').set_index('trade_date').total_value.astype(float)
        initial=float(payload['metadata']['initial_capital'])
        chart=pd.DataFrame({'策略净值':equity/initial})
        peak=equity.cummax().clip(lower=initial)
        tabs=st.tabs(['净值','回撤','原始图表','完整报告'])
        with tabs[0]: st.line_chart(chart)
        with tabs[1]: st.area_chart(pd.DataFrame({'回撤':equity/peak-1}))
        with tabs[2]:
            candidates=list((ROOT/'reports').glob(f'**/task_{tid}/report.json'))
            found=None
            for candidate in candidates:
                try:
                    if json.loads(candidate.read_text(encoding='utf-8'))==payload:
                        found=candidate.parent; break
                except (OSError,ValueError): pass
            if found:
                for name in payload.get('files',[]):
                    if name.endswith('.png') and Path(name).name==name and (found/name).exists(): st.image(str(found/name),use_container_width=True)
            else: st.info('未找到与当前完整报告匹配的本机图片；仍可查看数据库曲线与指标。')
        with tabs[3]: st.json(payload)
        st.download_button('下载绩效报告 JSON',json.dumps(payload,ensure_ascii=False,indent=2),f'task_{tid}_report.json','application/json')
    st.subheader('任务对比')
    if not reports.empty:
        ids=st.multiselect('选择需要对比的任务',reports.task_id.tolist(),default=reports.task_id.tolist()[-2:])
        comparison=[]
        for r in reports[reports.task_id.isin(ids)].itertuples():
            p=r.metrics_json; metrics=p['metrics']; meta=p['metadata']
            comparison.append({'任务':r.task_id,'股票':meta['symbol'],'批次':meta['batch_id'],'开始':meta['start'],'结束':meta['end'],'初始资金':meta['initial_capital'],'参数':str(meta['parameters']), '最终资产':metrics['final_equity'],'收益率':percent(metrics['total_return']),'最大回撤':percent(metrics['max_drawdown']),'成交笔数':metrics['trade_count']})
        display(pd.DataFrame(comparison))
        st.caption('比较前请确认股票、批次、日期、资金和成本口径一致。')
