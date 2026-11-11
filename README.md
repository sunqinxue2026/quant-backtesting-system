# Python Quantitative Data Processing and Backtesting System

面向国内初级量化开发工程师求职作品的日频股票研究型回测系统，支持 Python 3.10+。

## 已实现功能

- CSV 行情数据源适配器、DataLoadRequest 和来源/复权/单位元数据
- 字段、日期、代码标准化；重复记录、冲突记录、OHLC、成交量和成交额校验
- SQLAlchemy 行情、数据批次、策略、任务、信号、订单、成交、快照和结果表
- 支持 MySQL 8.0 和 SQLite 测试，数据库连接通过 `DATABASE_URL` 配置
- 日收益率、累计收益率、SMA、EMA、滚动波动率、成交量均线
- 双均线交叉策略：收盘产生信号，下一交易日开盘执行
- 单股票、现货、仅做多、无杠杆组合管理
- 交易单位、资金不足、最低佣金、卖出印花税、基点滑点和 T+1 可卖限制
- 订单状态：`FILLED`、`REJECTED`、`EXPIRED`
- 总收益率、自然日年化收益率、年化波动率、最大回撤、夏普比率、胜率、盈亏比和平均持仓时间
- 账户快照、订单报告、净值曲线、回撤曲线、价格均线信号图和策略/基准对比图
- pytest 核心业务测试、交易规则测试和 SQLite 数据库事务测试
- 阶段验收总结：`docs/阶段验收报告.md`
- 后续开发必须遵守的阶段闸门和固定汇报模板：`docs/开发流程与阶段闸门.md`

## 分阶段开发规则

本项目按需求书分七个阶段推进：环境与总体设计、行情读取与清洗、数据库与访问层、指标与策略、回测引擎与账户管理、绩效与可视化、测试修复与文档。

每个阶段只实现本阶段范围，完成后必须实际运行相关测试，并按以下 11 项格式汇报：

1. 本阶段目标
2. 新增或修改的文件
3. 已实现的功能
4. 运行过的命令和测试结果
5. 核心数据结构、算法和公式
6. 采用该方案的原因
7. 可选替代方案
8. 性能瓶颈和后续优化方向
9. 面试官可能追问的问题及回答思路
10. 尚未完成的内容
11. 下一阶段开始前需要确认的事项

第 11 项汇报后暂停，只有用户明确确认，才进入下一阶段。详细执行边界见 `docs/开发流程与阶段闸门.md`。

说明：现有 Git 历史曾经集中提交过多个业务模块，不能被改写成真实的逐阶段开发记录。`docs/阶段验收报告.md` 是已有总结；从阶段闸门文档提交后开始，新增开发按阶段单独提交、单独测试、单独汇报和等待确认。

## 安装与测试

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

项目已使用 Python 3.10.11 验证。当前全量测试结果：

```text
13 passed
```

如果终端或 PyCharm 继承了外部 Python 库路径，先执行：

```powershell
$env:PYTHONPATH=""
$env:PYTHONNOUSERSITE="1"
```

## 运行演示

不传 CSV 参数时，`main.py` 自动使用明确标记为 `synthetic/test` 的循环演示数据：

```powershell
.\.venv\Scripts\python.exe main.py
```

也可以指定测试数据和输出目录：

```powershell
.\.venv\Scripts\python.exe main.py data\test\synthetic_demo.csv --short 2 --long 3 --output reports\demo
.\.venv\Scripts\python.exe main.py data\test\synthetic_cycle_demo.csv --short 2 --long 3 --output reports\cycle_demo
```

运行后会生成：

- `quality_report.json`：数据质量、来源、复权口径、单位、策略和费用配置
- `metrics.json`：绩效指标
- `account_snapshots.csv`：每日现金、持仓、估值和收益
- `orders.json`：订单日期、方向、数量、状态和原因
- `equity_curve.png`：账户净值曲线
- `drawdown_curve.png`：最大回撤曲线
- `price_signals.png`：价格、均线和买卖信号
- `strategy_vs_benchmark.png`：策略与输入股票买入持有基准对比

测试数据只用于验证流程，不代表真实市场收益。使用真实来源历史数据时，必须同时记录来源、数据日期、复权口径和单位，不能把示例数据当作真实市场数据。

真实 CSV 至少需要字段：

```text
symbol,trade_date,open,high,low,close,volume,amount
```

股票代码要求使用类似 `600000.SH`、`000001.SZ` 的格式。

## PyCharm 运行配置

- Python 解释器：项目 `.venv` 中的 Python 3.10 或更高版本
- 工作目录：项目根目录
- 脚本路径：项目根目录下的 `main.py`
- 脚本参数：可以留空；留空会运行 synthetic/test 演示，也可以填写：

```text
data/test/synthetic_demo.csv --short 2 --long 3 --output reports/demo
```

## 数据库

默认使用：

```text
sqlite:///quant_backtesting.db
```

连接 MySQL 时设置环境变量：

```powershell
$env:DATABASE_URL="mysql+pymysql://user:password@localhost:3306/quant_db?charset=utf8mb4"
```

然后调用 `quant_system.database.create_session_factory()`。初始化说明见 `database/migrations/001_init.sql`。正式环境建议使用 Alembic 管理增量迁移。

## 交易时序和研究边界

`t` 日收盘后使用截至当日的数据生成信号，最早在下一可交易日开盘执行。买入成交价按滑点上浮，卖出成交价按滑点下调；当日买入的持仓不能当日卖出。最后交易日产生的信号记为 `EXPIRED`，不能用最后收盘价假设成交。

这是研究型历史回测系统，不连接真实券商，不发送真实订单。第一版暂不实现实时行情、多资产组合、分钟级回测、涨跌停、完整停牌日历和公司行动现金流还原。
