# 当前交付：第八阶段 Web 演示界面（等待验收）

第七阶段已获用户验收。新增 Streamlit 网页入口 `web_app.py`，提供系统总览、数据管理、创建回测、任务逐日回放和绩效对比。默认显示已有第七阶段 SQLite 手动演示库，也可选择独立网页库或环境变量数据库。

安装网页依赖并启动（项目根目录）：

```text
.venv\Scripts\python.exe -I -m pip install -e ".[test,web]"
.venv\Scripts\python.exe -I -X utf8 -m streamlit run web_app.py --server.headless=true --browser.gatherUsageStats=false
```

本轮全量143项测试通过（新增6项网页测试），保留2条既有FutureWarning。浏览器首页确认1个批次、2个任务、2份绩效、484条行情。新网页MySQL写入尚未现场实测。本机单用户界面不提供账号、跨会话提交锁和公网部署。完整11项说明见 `docs/阶段8_Web演示界面验收.md`。

网页新增“使用教程”导航，提供快速上手、逐日回放、报告解读、创建与对比四部分说明，可下载 `docs/量化研究工作台_使用教程.pdf`。教程不依赖数据库连接。

## 第七阶段历史交付（已验收）

第六阶段已验收。第七阶段新增 scripts/run_final_demo.py、8项回归用例，补齐Matplotlib依赖与面试说明。全量137项通过，保留2条测试夹具Pandas FutureWarning。

```text
.venv\Scripts\python.exe -I -m pip install -e ".[test]"
.venv\Scripts\python.exe -I -X utf8 -m pytest -o "pythonpath=src ." -q
.venv\Scripts\python.exe -I -X utf8 scripts\run_final_demo.py --csv "真实行情CSV" --provenance "来源JSON" --output reports/stage7/local
```

CSV使用标准8列；来源JSON包含source、symbol、data_as_of、price_type、is_synthetic=false、units、csv_sha256。来源及单位必须真实，不能把合成数据用于市场有效性证明。原始行情未获再分发许可，不随仓库提交，需要用户自行提供。来源摘要不符会拒绝。运行默认SQLite；MySQL需预先创建独立库，在本机配置DATABASE_URL，并增加 --database configured，密码不得提交。

入口复用同来源同摘要已校验批次，每次新建回测任务和报告目录。verification.json包含数据库回读结果；读取报告JSON时仅浮点允许rel_tol=1e-12、abs_tol=1e-14的序列化末位误差，其他类型及结构精确匹配；快照金额精确核对。

2026-11-13真实MySQL任务4/5均复用批次1：平安银行000001.SZ、2023-01-03至2024-12-31、484行全部accepted、SMA5/20、初始100000元、每次100股；33信号/33订单/33成交/484快照，最终99644.98元，完整平仓16次、未平仓1次。数据库JSON、执行数量、逐日快照回读均passed。旧任务1/2/3实际已提交并保留，曾因JSON浮点严格相等而误报失败，不能据此声称事务回滚。

结果总收益-0.35502%，最大回撤-0.3925%，价格基准-15.03268%。基准满仓无限分割、策略固定100股，仓位不同；且未核对公司行动和交易日历，未复权行情没有分红现金流还原，不证明策略有效。

2026-11-13用户在PyCharm使用系统Python（非项目.venv，选项-I -X utf8）手动运行SQLite最终演示两次：任务1/2、批次均为1，reused_batch分别为false/true；均为484条accepted、33信号/33订单/33成交/484快照，最终99644.98元，database_readback=passed、退出码0。证据为用户提供的完整日志，本次文档更新未重跑测试或独立查询数据库，未独立检查旧文件不变性及本次四图；不与MySQL任务编号混淆。详见第七阶段报告的用户手动演示补充。

完整11项验收：docs/阶段7_完整验证与最终验收.md。安装、来源契约和讲解：docs/面试讲解与复现.md。文件与数据库非原子、首次并发文件无锁、无完整停牌涨跌停撮合、无多股票与部分平仓，详见报告。下面是历史阶段说明，过往测试数量不是当前总数。

---

## 第六阶段：绩效与图表（历史记录，已验收）

第五阶段已获用户验收。第六阶段实现从已保存任务重读快照、成交及同批次行情，计算绩效、基准并输出四张PNG、日序列CSV和报告JSON，写入backtest_result。全量129项测试通过（新增21项），保留两条既有Pandas FutureWarning。

先运行第五阶段run_pipeline.py，再使用实际任务ID：

```text
.venv\Scripts\python.exe -I scripts\analyze_task.py --task-id 1
```

默认读取第五阶段SQLite演示库，不读取DATABASE_URL。真实数据库需显式添加 --database configured，并在本机配置DATABASE_URL。已补充真实MySQL任务1绩效报告生成（用户PyCharm系统Python、退出0）及Navicat核验：quant_db中绩效记录1条、任务completed、2信号/2订单/2成交/9快照。本轮已通过独立MySQL会话逐字段比较全部85个JSON叶子值；重复生成被拒绝且六个文件摘要不变；两会话对已有任务并发重复写入均返回1062并回滚。其余3图通过图像识别完成内容复核，四图均有查看证据。首次并发生成与文件互斥未验证，详见第六阶段报告。

--annualization-days 默认252；--risk-free-rate为年化小数，默认0；--output指定报告根目录。任务文件夹包含净值、回撤、价格均线信号和基准对比四张PNG、curves.csv和report.json。

已保存绩效的任务拒绝重复保存；重跑回测产生新任务。文件和SQL不是原子事务：文件失败不写绩效，SQL提交失败可能留下文件，不应据此认为保存成功。

绩效口径：首日收益以初始资金为分母，回撤峰值包含初始资金；年化收益按首末快照自然日跨度以365.25折算；波动ddof=1；无风险利率几何日化。无样本或零波动等未定义统计返回null并说明原因。未平仓市值计入资产，不计胜率。基准是同批次同日期同口径收盘价归一化、无成本且无限分割买入持有，不是可执行对照账户。

9日合成演示最终资产9700、总收益-3%、最大回撤-3%、基准-20%、完整平仓1次、持仓3个交易日。短样本年化仅核验公式，不证明策略有效性。

```text
.venv\Scripts\python.exe -I -m pytest -o "pythonpath=src ." -q
```

完整11项说明见 docs/阶段6_绩效指标与图表验收.md。第六阶段已获用户验收。以下早期阶段测试数量和阶段状态为历史记录。

# 量化金融数据处理与策略回测系统：逐阶段重写版

目标：使用Python 3.10、Pandas、NumPy、MySQL8、SQLAlchemy、Matplotlib、pytest，从空项目逐阶段建立可理解、可测试的日频研究型回测系统。

## 当前状态

第一至第七阶段已获用户验收。第八阶段Web界面已实现，当前全量143项测试通过，等待界面验收。第七阶段历史记录为137项通过，独立MySQL数据库quant_stage7_validation的任务4/5均完整回读通过。详见文首和各阶段报告。

第五阶段运行方法（项目根目录，使用项目虚拟环境）：

```text
.venv\Scripts\python.exe -I -m pytest -o pythonpath=src -q
.venv\Scripts\python.exe -I scripts\run_backtest_demo.py
```

演示仅使用synthetic/test合成行情，不连接数据库，生成execution.json和snapshots.csv。持久化服务为 `quant_system.engine.persistence.save_execution`，在调用方事务中保存订单、成交、快照；新增执行持久化及CSV全链路已用SQLite验证，已于2026-11-13补充真实MySQL订单、成交及账户快照实测，详见第五阶段报告。

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

数据库使用方式见下文；第四阶段指标和策略测试命令及结果见 `docs/阶段4_技术指标与双均线策略验收.md`。第五阶段回测演示命令见文首；第六阶段绩效和图表运行方法见文首。

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

第三阶段已经用 SQLite 验证模型建表、批量行情写入、日期范围查询、唯一约束和事务回滚。已有 Navicat + MySQL 8.0.37 手工建表与事务验证；新增导入脚本已完成真实 MySQL 正常导入，用户补充相同参数第二次运行退出码 1、两次查询均为 1 个批次和 2 条行情的手动验证证据；旧日志未展示底层编号；后续用户提供新版真实日志，已捕获 IntegrityError / db_code=1062 / 重复键冲突（退出码1），详见 `docs/阶段3_数据库与数据访问层验收.md`。

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

第三阶段历史全量测试：35 个用例全部通过，其中新增 6 个导入端到端用例。命令行 SQLite 演示：6 条输入，accepted=2、review=1、rejected=2、duplicate_removed=1，成功入库 2 条。新脚本的真实 MySQL 手动验证使用 synthetic_gui_test_01：首次 batch_id=7、写入 2 条、退出 0；重复运行退出 1，用户反馈数量仍为 1 个批次、2 条行情；新版真实日志已捕获 IntegrityError / db_code=1062 / 重复键冲突。真实 MySQL 自动化集成验证尚未实现。第四阶段完成后全量回归测试为 66 项通过，详见 `docs/阶段4_技术指标与双均线策略验收.md`。


## 第三阶段错误日志整改

入口已支持安全分类数据库错误：重复键的真实驱动错误为 1062 时，显示 `type=IntegrityError db_code=1062 reason=重复键冲突`；其他约束和连接问题分别分类，不输出异常正文、SQL、参数或连接串。数据库初始化失败也统一处理。失败仍退出 1。

第三阶段错误日志整改全量测试为 45 项通过（新增 10 项安全日志测试）；1062 分类测试使用模拟驱动异常，随后用户以相同 PyCharm 参数运行，新版真实日志显示 `type=IntegrityError db_code=1062 reason=重复键冲突`，退出码 1，现场日志核验已完成。数量不变引用此前 Navicat 截图及用户两次查询反馈，详见第三阶段验收文档。第四阶段报告见 `docs/阶段4_技术指标与双均线策略验收.md`，第四阶段已验收，第五阶段实现与验证结果见文首和第五阶段报告。


## 第五阶段补齐：统一CSV/批次回测入口

完整链路：CSV读取清洗 → 导入批次和行情提交 → 指定批次查询 → 标准DataFrame → 指标 → 策略 → 次日开盘执行 → 配置、任务、信号、订单、成交、快照原子保存。

首次运行独立SQLite演示（synthetic/test合成数据，零成本，不代表市场收益）：

```text
.venv\Scripts\python.exe -I scripts\run_pipeline.py --csv data/test/synthetic_pipeline_demo.csv --source synthetic/test --data-as-of 2024-01-12 --synthetic --price-type 未复权 --symbol 000001.SZ --start 2024-01-02 --end 2024-01-12 --zero-cost
```

默认数据库为 reports/stage5_pipeline/demo.db，不读取DATABASE_URL。首次导入预期批次1、任务1、2信号、2订单、2成交、9快照、最终资产9700.00。重复相同CSV导入会触发唯一约束；不要改价格口径规避。重跑已有批次应改用：

```text
.venv\Scripts\python.exe -I scripts\run_pipeline.py --batch-id 1 --price-type 未复权 --symbol 000001.SZ --start 2024-01-02 --end 2024-01-12 --zero-cost
```

以实际batch_id替换1；每次重跑创建新任务，旧任务结果不覆盖。
使用已配置数据库必须明确增加 --database configured，并在本机设置DATABASE_URL；连接串不入库、不打印。MySQL写入使用项目专用数据库；2026-11-13已在quant_db完成合成数据完整链路、带成本精度、重复保存和强制异常回滚实测，不删除已有数据。

指标函数在DataFrame.attrs记录均线参数，策略在元数据存在时拒绝参数不匹配；统一入口保证由同一参数计算并运行。手工构造的旧式指标帧仍兼容，若attrs缺失则无法单靠列名证明周期，调用方须保证来源。

新增14项测试：全链路手算及入库查询、分类与批次隔离、4项输入边界、执行事务回滚、成本传递、未来数据不变性、参数不匹配及4项信号契约错误。全量108项通过，保留2条既有测试数据类型FutureWarning。

## 第五阶段真实MySQL补充验证（2026-11-13）

localhost:3306 / quant_db：新增合成行情批次10（9行）；零成本任务1保存2信号、2订单、2成交、9快照，最终9700.00；带成本任务2最终9670.21。新会话逐字段核对订单日期、成交价、费用、关联及全部快照。重复保存被拒绝且数量不变；任务3在保存后主动抛错，配置、任务、信号、订单、成交、快照整体回滚，原行情保留。实际保留2个测试任务、4信号、4订单、4成交、18快照。未进入第六阶段。108项为此前SQLite全量测试记录，本轮未重跑。
