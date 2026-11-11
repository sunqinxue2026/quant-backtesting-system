CREATE DATABASE IF NOT EXISTS quant_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE quant_db;

-- 第三阶段使用 SQLAlchemy Base.metadata.create_all 创建表。
-- 本文件负责创建数据库和记录初始化约定；正式增量变更建议使用 Alembic。
-- 表：stock_basic、data_import_batch、stock_daily、strategy_config、backtest_task、
-- backtest_signal、backtest_order、backtest_trade、backtest_snapshot、backtest_result。
-- stock_daily 唯一键：symbol + trade_date + price_type。
-- backtest_signal、backtest_snapshot 分别按 task_id + 日期保持幂等。
