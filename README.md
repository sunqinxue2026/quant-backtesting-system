# 量化金融数据处理与策略回测系统：逐阶段重写版

目标：使用Python 3.10、Pandas、NumPy、MySQL8、SQLAlchemy、Matplotlib、pytest，从空项目逐阶段建立可理解、可测试的日频研究型回测系统。

## 当前状态

第三阶段“数据库与数据访问层”已完成，等待确认后进入第四阶段。当前重写版已实现数据库模型、Repository 和 CSV 清洗结果原子入库脚本；端到端自动化验证使用 SQLite，并已补充 PyCharm 导入与 Navicat 查询的真实 MySQL 手动验证；指标、策略和回测仍未实现。

- 需求基线：`需求书.md`。项目按用户要求以 Python 3.10 为主要兼容版本设计。
- 第一阶段报告：`docs/阶段1_总体设计与验收.md`。
- 第二阶段报告：`docs/阶段2_CSV读取与数据清洗验收.md`。
- 第二阶段测试：25项全部通过；清洗演示已生成 cleaned、review、rejected 和 quality_report 文件。
- 本阶段已建立独立 .venv，使用 Python 3.10.11、Pandas 2.3.3、NumPy 2.2.6、pytest 9.2.0 验证通过。
- 已通过 Navicat Premium 17 连接 localhost:3306 的 MySQL 8.0.37，完成项目专用数据库 quant_db 的建表、写入、查询、唯一约束和事务回滚验证；重复插入被错误 1062 拒绝，回滚后行情数量仍为 2 条。

## 与旧版本的关系

本分支为`phased-rewrite`，从独立初始提交开始；同一GitHub仓库的`main`保留旧集中开发版本。旧目录、代码和提交没有删除或重写。新项目不复制旧业务代码，阶段报告不引用旧13项测试作为新项目成绩。

## 七阶段路线

1. 环境检查、总体架构、目录、数据库和规则设计。
2. 独立Python3.10环境、工程骨架、CSV读取、清洗和对应测试。
3. MySQL模型、真实DDL、访问层、事务与真实MySQL验证。
4. 技术指标、Strategy接口、双均线信号及测试。
5. 回测时序、订单成交、资金持仓和手工确定性测试。
6. 绩效公式、基准、图表及边界测试。
7. 全量验证、真实CSV/MySQL演示、README与面试说明。

每阶段只能实现本阶段内容；结束必须逐项输出：目标、文件、功能、命令/测试、数据结构/算法/公式、原因、替代方案、瓶颈、面试问答、未完成内容、下阶段确认事项。汇报后停止，收到用户明确确认才进入下一阶段。第一阶段只做环境检查与设计，不编写业务代码。

## 第二阶段安装与测试

本阶段已实际验证：

```powershell
$env:PYTHONPATH=""
$env:PYTHONNOUSERSITE="1"
.\.venv\Scripts\python.exe -m pytest tests\data tests\cleaning -q
.\.venv\Scripts\python.exe main.py --output reports\cleaning_demo
```

当前第二阶段测试结果：`25项全部通过`。入口会读取 `data/test/synthetic_cleaning_demo.csv`，输出清洗结果和质量报告。测试数据只用于验证流程，不代表真实市场收益。

数据库使用方式见下文；指标、策略、回测和图表命令将在对应阶段实现且实际验证后补充。

## 第二阶段整改验收

拒绝输出保留原始字段、来源记录号和原因；统计与明细一致。股票代码只接受六位代码加SH/SZ后缀，规范大小写和空格，不猜测裸代码市场。repaired统计代码格式实际修复行数，普通日期和数值类型转换不计入。完整11项验收见第二阶段报告；此处为第二阶段历史记录，当前状态见文首。

## 第三阶段数据库使用

默认数据库连接为：

```text
sqlite:///quant_backtesting.db
```

设置 MySQL 8.0 连接时使用环境变量：

```powershell
$env:DATABASE_URL="mysql+pymysql://user:password@localhost:3306/quant_db?charset=utf8mb4"
```

在 Python 中调用 `quant_system.database.create_session_factory()` 会创建模型表并返回 SQLAlchemy 会话工厂。数据库创建和字符集约定见 `database/migrations/001_init.sql`，配置模板见 `.env.example`。

第三阶段已经用 SQLite 验证模型建表、批量行情写入、日期范围查询、唯一约束和事务回滚。已有 Navicat + MySQL 8.0.37 手工建表与事务验证；新增导入脚本已完成真实 MySQL 正常导入，用户补充相同参数第二次运行退出码 1、两次查询均为 1 个批次和 2 条行情的手动验证证据；第二次日志未展示底层错误编号，详见 `docs/阶段3_数据库与数据访问层验收.md`。

## 第三阶段补充：CSV 清洗结果自动入库

使用项目 Python 3.10 环境。先通过环境变量 DATABASE_URL 指定项目数据库；不设置时使用默认 SQLite。MySQL 示例见 .env.example（模板不会自动加载，真实密码不得提交）。在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\import_market_data.py data\test\synthetic_cleaning_demo.csv --source synthetic/test --data-as-of 2024-01-03 --price-type "前复权研究口径" --synthetic --output reports\import_demo
```

真实 CSV 必须明确填写真实来源、截至日期、价格口径和单位，不添加 --synthetic；成交量等单位可用 --volume-unit、--amount-unit、--price-unit 指定。当前仅记录单位，不自动换算。

- 只写入 accepted；review、rejected 不进入行情表，完全重复不重复写入。
- 批次与行情在同一事务内；数据库唯一键冲突报错，整批回滚，不覆盖、不跳过。再次运行同一文件会失败，这是既定重复导入策略。
- 无 accepted 时保存 no_accepted 批次，行情为零。
- 价格按 6 位、成交量/额按 4 位小数 ROUND_HALF_EVEN 入库。
- 现有 units_json 保留单位，并新增 _metadata、_quality_report 嵌套对象保存文件摘要和完整质量报告，无表结构变更。
- 成功输出 batch_id、inserted_rows 和 committed 状态；明细输出 accepted.csv、review.csv、rejected.csv、import_report.json。
- 数据库提交与报告写出不是同一事务：报告写出失败会提示已提交批次 ID 并退出 2，勿盲目重复导入。输入或写入失败退出 1，详细失败类型可由服务层异常定位。

本次全量测试：35 个用例全部通过，其中新增 6 个导入端到端用例。命令行 SQLite 演示：6 条输入，accepted=2、review=1、rejected=2、duplicate_removed=1，成功入库 2 条。新脚本的真实 MySQL 手动验证使用 synthetic_gui_test_01：首次 batch_id=7、写入 2 条、退出 0；重复运行退出 1，用户反馈数量仍为 1 个批次、2 条行情。通用错误日志未显示底层编号；真实 MySQL 自动化集成验证尚未实现。35 项通过为此前结果，本次文档更新未重跑测试。


## 第三阶段错误日志整改

入口已支持安全分类数据库错误：重复键的真实驱动错误为 1062 时，显示 `type=IntegrityError db_code=1062 reason=重复键冲突`；其他约束和连接问题分别分类，不输出异常正文、SQL、参数或连接串。数据库初始化失败也统一处理。失败仍退出 1。

本轮全量测试 45 项通过（新增 10 项安全日志测试）；1062 测试使用模拟驱动异常，不代表本轮实际连接 MySQL。前文 35 项及通用日志为历史验证记录。需要以原 PyCharm 配置再次运行后，根据实际错误编号及 Navicat 数量核验补充真实证据，不能改写旧日志。完整 11 项整改报告见第三阶段验收文档。
