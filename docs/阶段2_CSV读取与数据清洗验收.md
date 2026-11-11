# 第二阶段：工程骨架、CSV 读取与数据清洗验收

日期：2026-11-12。状态：本阶段完成，等待用户确认后进入第三阶段。

## 1. 本阶段目标

建立 Python 3.10+ 可运行工程骨架，实现 CSV 行情数据读取、来源元信息封装、字段和类型标准化、重复与冲突记录识别、OHLC/成交数据质量检查、清洗质量报告和对应 pytest 测试。

本阶段没有实现数据库、SQLAlchemy、技术指标、策略、回测、绩效或图表功能。

## 2. 新增或修改的文件

- `pyproject.toml`：Python 3.10 至 3.11 兼容范围、src 包发现、pytest 配置。
- `requirements.txt`：Pandas、NumPy、pytest 依赖范围。
- `main.py`：第二阶段清洗演示入口，自动引导 `src` 路径。
- `src/quant_system/__init__.py`：包版本。
- `src/quant_system/data/__init__.py`、`models.py`、`loader.py`：数据请求、元数据、行情对象和 CSV 适配器。
- `src/quant_system/cleaning/__init__.py`、`models.py`、`cleaner.py`：质量报告和清洗流程。
- `data/test/synthetic_cleaning_demo.csv`：明确标记为 synthetic/test 的清洗样例。
- `tests/data/__init__.py`、`tests/data/test_loader.py`：CSV 读取测试。
- `tests/cleaning/__init__.py`、`tests/cleaning/test_cleaner.py`：清洗、重复、冲突和 OHLC 测试。
- `docs/阶段2_CSV读取与数据清洗验收.md`：本阶段 11 项验收记录。
- `README.md`：更新重写版当前阶段和运行命令。

未纳入本阶段提交：已有的 `.idea/` 未跟踪目录；它属于本机 IDE 配置，不是项目代码。

## 3. 已实现的功能

- CSV 文件存在性和空文件检查。
- 字段别名标准化，例如中文列名、`code/date` 等映射到统一字段。
- 必需字段检查：`symbol`、`trade_date`、`open`、`high`、`low`、`close`、`volume`、`amount`。
- 数据来源、文件名、数据截至日期、复权口径、单位、synthetic 标志和文件 SHA-256 元信息封装。
- 股票代码格式检查，保留六位代码前导零，要求 `000001.SZ` 或 `600000.SH` 形式。
- 交易日期转换和数值字段转换。
- 完全重复行情识别：保留一条，其余计入 `duplicate_removed`。
- 同股票同日期冲突记录识别：整组计入拒绝并记录原因。
- 缺失值、非法日期、非有限数值检查。
- OHLC 逻辑检查：价格为正、最高价不低于开收盘价、最低价不高于开收盘价、最高价不低于最低价。
- 成交量和成交额非负检查；零成交记录进入 `review`，不进入 accepted。
- 按股票代码和交易日期升序排列。
- 输出 accepted、review、rejected 三类 CSV 和 JSON 质量报告。
- 质量报告记录输入、输出、接受、人工确认、拒绝、重复删除、修复数量和原因。
- `main.py` 直接运行时自动加入项目 `src` 路径，不要求用户先设置 `PYTHONPATH`。

## 4. 运行过的命令和测试结果

在 `D:\code\quant-backtesting-system-rewrite` 执行：

```powershell
$env:PYTHONPATH=''
$env:PYTHONNOUSERSITE='1'
python --version
```

实际 Python 版本：`Python 3.12.14`。项目声明兼容 Python 3.10 至 3.11；本机本阶段使用的 Python 3.12 运行验证通过，但仍需在 Python 3.10 环境再做兼容性验证。

```powershell
python -m pytest tests\data tests\cleaning -q
```

结果：`5 passed`。

```powershell
python main.py --output reports\cleaning_demo
```

结果：命令成功，生成：

- `reports/cleaning_demo/cleaned.csv`
- `reports/cleaning_demo/review.csv`
- `reports/cleaning_demo/rejected.csv`
- `reports/cleaning_demo/quality_report.json`

演示质量报告实际统计：输入 6 行，接受 2 行，人工确认 1 行，拒绝 2 行，完全重复删除 1 行，修复 0 行。

测试过程中曾发现直接运行入口时无法导入 `quant_system`，原因是 src 布局尚未加入运行路径；已在 `main.py` 修复并重新运行通过。清洗测试仍会对故意设置的非法日期给出 Pandas 的日期格式提示，不影响拒绝结果；后续可在兼容性阶段统一日期解析策略。

## 5. 核心数据结构、算法和公式

- `DataLoadRequest`：输入路径、来源名、数据截至日期、复权口径、单位和 synthetic 标志。
- `DatasetMetadata`：来源文件、SHA-256、日期、复权口径、单位和测试标识。
- `MarketData`：标准化前 DataFrame 加元数据。
- `CleanResult`：accepted、review、rejected 三个 DataFrame 加 `QualityReport`。
- `QualityReport`：输入输出数量、各终态数量、原因计数和元数据。

清洗终态互斥分类为：

```text
accepted + review + rejected + duplicate_removed = 输入总行数
```

`repaired` 是附加统计，不参与终态相加。

OHLC 核心校验：

```text
open > 0
high > 0
low > 0
close > 0
high >= max(open, close)
low <= min(open, close)
high >= low
volume >= 0
amount >= 0
```

完全重复按 `symbol + trade_date` 分组后比较数值字段；同键不同数值视为冲突，整组拒绝。输出排序键为 `(symbol, trade_date)`。

## 6. 采用该方案的原因

CSV 读取和清洗分离，便于后续接入其他数据源而不修改策略或回测模块。数据元信息与行情数据一起传递，可以追踪来源和复权口径。`accepted/review/rejected/duplicate_removed` 的分类让自动修复、人工确认和直接拒绝边界清晰，避免用 `fillna(0)` 制造虚假行情。质量报告采用结构化 JSON，便于后续第三阶段导入批次时保存。

## 7. 可选替代方案

- 使用 Pydantic 或 Pandera 做 DataFrame schema 校验。
- 使用 Great Expectations 管理质量规则和数据验证报告。
- 大文件使用 Polars 或 Pandas `chunksize` 分块读取。
- 使用配置文件维护字段映射，而不是当前代码内的别名表。
- 使用 `pathlib` 之外的对象存储 URI 适配器支持远程数据源。

这些方案暂未实现，因为本阶段重点是让核心规则由项目代码直接表达并可测试。

## 8. 性能瓶颈和后续优化方向

当前实现一次性读取 CSV，适合本阶段小型日线数据。大文件的主要瓶颈是内存占用、重复分组和 DataFrame 拷贝。后续可增加分块读取、批量质量统计、Parquet 中间格式和矢量化规则。但分块处理必须跨块维护 `symbol + trade_date` 冲突状态，不能只加 `chunksize` 就认为结果等价。

## 9. 面试官可能追问的问题及回答思路

**为什么不统一用 `fillna(0)`？**

价格缺失和成交量缺失的业务含义不同。填 0 会制造不可能的价格或成交记录，所以关键字段缺失直接拒绝，零成交进入人工确认。

**如何处理重复行情？**

完全相同的重复记录保留一条并记录删除数量；同股票同日期但价格或成交数据不同，无法安全判断哪条正确，因此整组拒绝并保留原因。

**为什么记录 SHA-256 和复权口径？**

相同文件可幂等识别，不同文件和不同价格口径不能悄悄覆盖。这样后续回测可以追溯输入数据。

**为什么数据源不能直接连接策略？**

数据源只负责读取和元数据，清洗负责质量控制，策略只消费标准化数据。解耦后可以替换 CSV、API 或数据库来源。

**为什么测试数据必须标记 synthetic/test？**

测试数据只能证明代码流程和边界规则，不能代表真实市场收益。显式标记可以防止把演示结果误当成策略研究结论。

## 10. 尚未完成的内容

- MySQL 表结构、SQLAlchemy 模型、批量入库和事务。
- 技术指标、双均线策略和信号持久化。
- 回测引擎、订单、成交、资金、持仓和 T+1。
- 绩效指标、基准和图表。
- 真实来源行情导入和交易日历校验。
- Python 3.10 虚拟环境下的本阶段复验；本轮使用 Python 3.12.14 验证通过。
- 非交易日、停牌和涨跌停的外部状态判断。

## 11. 下一阶段开始前需要确认的事项

第二阶段已完成，下一阶段是第三阶段“数据库和数据访问层”。开始前需要确认：

1. 是否进入第三阶段。
2. 是否使用本机 MySQL 8.0 服务和 Navicat Premium 17辅助核验。
3. MySQL 数据库名称是否采用第一阶段设计的 `quant_db`。
4. 真实数据库账号密码只在本机配置，不写入 Git、报告或对话文件。

本报告完成后停止开发，未实现第三阶段内容，等待用户明确确认。
