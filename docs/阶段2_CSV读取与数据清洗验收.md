# 第二阶段：CSV读取与数据清洗验收

日期：2026-11-12。状态：第二阶段整改与验证完成，等待用户验收；未进入第三阶段。

## 1. 本阶段目标

建立独立Python 3.10环境，实现工程骨架、CSV读取、来源元数据、字段标准化、数据质量分类和测试。不实现数据库、指标、策略或回测。

## 2. 新增或修改的文件

本阶段已有：pyproject.toml、requirements.txt、main.py、src/quant_system包及data/cleaning模块、data/test/synthetic_cleaning_demo.csv、tests/data和tests/cleaning、README.md及本报告。

本次整改修改：main.py、data/loader.py、cleaning/cleaner.py、tests/data/test_loader.py、tests/cleaning/test_cleaner.py、README.md、本报告。独立.venv和reports运行产物不提交；不修改旧项目。

## 3. 已实现的功能

- CSV路径、空文件、无数据行、字段缺失及别名映射冲突检查。
- MarketDataSource Protocol与CSV适配器，来源元数据及SHA-256。
- 按字符串读取，保护代码前导零；代码去空格、后缀转大写。
- 遵守第一阶段规则：只接受六位代码加SH/SZ后缀，不猜测裸代码交易所。
- 日期和数值转换、缺失和非有限值检查、OHLC和非负成交校验。
- 完全重复去重；同键数据冲突整组拒绝，比较时缺失值参与判断。
- 零成交进入review；accepted/review/rejected输出包含来源记录号、原始字段和处理状态、原因。
- 所有拒绝路径统一保留明细，不再中途丢弃非法日期、代码或冲突组。
- 来源记录号从1计数，指CSV数据记录序号，不声称是含多行引号字段文件的物理行号。
- repaired为代码空格或大小写被修复的输入记录数；日期/数值常规类型转换不计修复。
- 输出按symbol、trade_date排序，质量报告带元信息、原因统计和数量守恒校验。
- loader、cleaner及入口增加logging；默认输入和输出相对项目根目录解析。
- 没有外部日历时明确记录calendar_status=unknown_without_external_calendar，不猜测停牌或漏数。

## 4. 运行过的命令和测试结果

本次实际执行：

```powershell
& 'D:\Program Files\Python\python.exe' -I -m venv .venv
.\.venv\Scripts\python.exe -I -m pip install -r requirements.txt
$env:PYTHONPATH=''
$env:PYTHONNOUSERSITE='1'
.\.venv\Scripts\python.exe -m pytest tests\data tests\cleaning -q
.\.venv\Scripts\python.exe main.py --output reports\cleaning_demo
```

环境：Python 3.10.11，Pandas 2.3.3，NumPy 2.2.6，pytest 9.2.0。测试25项全部通过，退出码0。

演示成功：输入6、accepted 2、review 1、rejected 2、duplicate_removed 1、repaired 0。生成cleaned.csv、review.csv、rejected.csv、quality_report.json。

测试涵盖正常读取、元数据摘要、缺列、文件不存在、空文件、无数据行、列名冲突、前导零、重复与冲突、原始拒绝明细、缺失值重复比较、代码修复、NaN/无穷、OHLC/负成交、日期数值转换、排序、空DataFrame和数量守恒。

之前的5项测试及Python3.12结果保留在历史提交，不能替代本次Python3.10验证。本次业务代码测试通过后未再修改业务代码。

## 5. 核心数据结构、算法和公式

DataLoadRequest承载读取请求；DatasetMetadata承载来源；MarketData封装DataFrame和元数据；CleanResult封装三类数据及QualityReport。

清洗为原记录建立_source_row、_raw_*、_row_status、_reason和_repaired。按固定优先顺序确定唯一终态；每条拒绝记录保存首个主拒绝原因，而非罗列所有同时存在的问题。

重复键为symbol+trade_date；按数值字段nunique(dropna=False)判断冲突，避免忽略缺失值。类型转换后数值等价的记录按相同记录处理。

输入数=accepted+review+rejected+duplicate_removed；repaired为附加标签，不参与相加。拒绝明细长度=报告rejected_rows。

OHLC均为正；high>=max(open,close)，low<=min(open,close)，high>=low；volume、amount>=0。

## 6. 采用该方案的原因

数据读取与质量规则分离，可替换数据源；Pandas向量化处理便于解释；保留原字段和来源行号便于追溯；分类隔离不确定数据，避免fillna(0)制造行情。Protocol不依赖数据库或策略。

## 7. 可选替代方案

Pandera验证DataFrame、Pydantic验证元数据、Polars处理大文件、配置化字段别名、独立质量规则对象。这些替代方案本阶段不引入。

## 8. 性能瓶颈和后续优化方向

当前一次性CSV加载、原始列副本、分组和排序会占用内存。大数据可分块或使用列式存储，但必须跨块维护重复键。未进行性能基准，不声称任何提速比例。

## 9. 面试官可能追问的问题及回答思路

- 为什么不fillna(0)？关键价格缺失不代表零，必须拒绝并留证。
- 为何nunique使用dropna=False？缺失与有效值不一致，忽略缺失会误删冲突记录。
- 统计守恒足够吗？还需拒绝明细一致、原字段和来源号可追溯，本阶段有测试。
- 为什么不推断裸代码市场？遵守已确认范围，保留原值并明确拒绝，避免错误映射。
- SHA-256证明真实性吗？只能标识内容，真实性依靠来源；测试数据明确synthetic/test。
- 每行为什么只有一个原因？固定优先级保证终态和主原因可解释，多问题诊断可后续扩展。

## 10. 尚未完成的内容

本阶段约定实现和本轮发现的验收缺陷已处理，并在Python3.10验证。边界：不接外部交易日历，不推断裸代码交易所，不修复未知单位或无法识别日期，不代表已验证真实市场行情。数据库、指标、策略、回测和绩效属于第三至第七阶段，未在本阶段实现。

## 11. 下一阶段开始前需要确认的事项

请用户验收本阶段实现、测试及上述边界。只有明确确认进入第三阶段后，才开发MySQL模型、DDL、访问层及事务。数据库账号密码不写入代码、报告或Git。当前停在第二阶段，不自动推进。
