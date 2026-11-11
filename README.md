# Python Quantitative Data Processing and Backtesting System

面向国内初级量化开发工程师求职作品的日频股票研究型回测系统。

## 已实现功能

- CSV 行情数据源适配器与质量报告
- 字段、日期、代码标准化；重复记录、OHLC、成交量和成交额校验
- SQLAlchemy 七张业务表，支持 MySQL 8.0 和 SQLite 测试
- 日收益率、累计收益率、SMA、EMA、滚动波动率、成交量均线
- 双均线交叉策略：收盘产生信号，下一交易日开盘执行
- 单股票、现货、仅做多、无杠杆组合管理
- 手续费、卖出印花税、滑点、交易单位和资金不足处理
- 账户净值、年化收益、波动率、最大回撤和夏普比率
- 净值曲线与价格信号图表
- pytest 核心业务测试与 SQLite 数据库事务测试
- 策略信号、订单、成交、每日账户快照和回测结果持久化

## 安装与测试

项目支持 Python 3.10 及更高版本，并在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

如果使用 PyCharm，请按下面方式配置运行环境：

- Python 解释器选择项目虚拟环境中的 Python 3.10 或更高版本；本项目已验证 Python 3.10.11。
- 工作目录设置为项目根目录 `D:\\code\\quant-backtesting-system`。
- 运行配置中的“脚本路径”选择项目根目录下的 `main.py`。
- “脚本参数”可以留空，直接运行会使用 synthetic/test 循环演示数据、2/3 日均线并输出到 reports/cycle_demo；也可以填写自定义参数，例如：

```text
data/test/synthetic_demo.csv --short 2 --long 3 --output reports/demo
```

- 环境变量中不要设置指向其他 Python 库目录的 `PYTHONPATH`。如果当前终端或 IDE 继承了外部 `PYTHONPATH`，请将它清空；PowerShell 可执行：

```powershell
$env:PYTHONPATH=""
$env:PYTHONNOUSERSITE="1"
```

现在直接运行 `main.py` 无需 CSV 参数，会自动运行明确标记的 synthetic/test 演示。默认数据路径与输出路径均相对于项目根目录解析，不依赖 IDE 工作目录。`main.py` 已内置 `src` 路径处理，因此在正确的项目解释器和工作目录下不需要手动设置 `PYTHONPATH`。

## 运行示例

测试数据明确标记为 synthetic/test，仅用于演示：

```powershell
python main.py data/test/synthetic_demo.csv --short 2 --long 3 --output reports/demo
```

运行成功后会生成质量报告、绩效指标 JSON、账户净值曲线 PNG 和价格均线信号图 PNG。若希望观察完整的买卖配对，可运行项目内明确标记为 synthetic/test 的循环演示数据：

```powershell
python main.py data/test/synthetic_cycle_demo.csv --short 2 --long 3 --output reports/cycle_demo
```

该文件只用于测试策略流程，不代表真实市场收益。使用真实来源历史数据时，胜率和盈亏比才具有研究解释价值。

真实 CSV 至少需要字段：`symbol,trade_date,open,high,low,close,volume,amount`。导入真实数据时必须同时记录来源、数据日期和复权口径，不能把示例数据当作真实市场数据。

## 数据库

默认使用 `sqlite:///quant_backtesting.db`。连接 MySQL 时设置：

```powershell
$env:DATABASE_URL="mysql+pymysql://user:password@localhost:3306/quant_db?charset=utf8mb4"
```

然后调用 `quant_system.database.create_session_factory()`，数据库表会由 SQLAlchemy 创建。初始化说明见 `database/migrations/001_init.sql`。

## 交易时序

`t` 日收盘后用当日均线交叉生成信号，最早在 `t+1` 交易日开盘执行。成交价按买入上滑、卖出下滑的滑点规则处理。研究结果不代表真实可成交收益，也不连接券商账户。
