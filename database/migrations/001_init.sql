CREATE DATABASE IF NOT EXISTS quant_db DEFAULT CHARACTER SET utf8mb4;
USE quant_db;

-- 生产环境先执行本文件创建数据库，再由 SQLAlchemy Base.metadata.create_all 建表。
-- ORM 表：stock_basic、data_import_batch、stock_daily、strategy_config、backtest_task、
-- backtest_signal、backtest_order、backtest_trade、backtest_snapshot、backtest_result。
-- stock_daily 唯一键：symbol + trade_date + price_type。
-- backtest_signal、backtest_snapshot 唯一键：task_id + 日期。
-- 所有批量行情写入必须在一个事务内完成；失败时回滚。
-- 正式生产环境建议使用 Alembic 管理增量迁移。
