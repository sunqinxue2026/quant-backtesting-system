CREATE DATABASE IF NOT EXISTS quant_db DEFAULT CHARACTER SET utf8mb4;
USE quant_db;

-- 生产环境可先执行本文件创建数据库，再由 SQLAlchemy Base.metadata.create_all 建表。
-- 项目当前通过 ORM 创建以下业务表：
-- stock_basic, stock_daily, strategy_config, backtest_task,
-- backtest_signal, backtest_order, backtest_trade, backtest_snapshot,
-- backtest_result
-- StockDaily 唯一键：symbol + trade_date
-- BacktestSignal 唯一键：task_id + signal_date
-- BacktestSnapshot 唯一键：task_id + trade_date
-- 正式生产环境建议使用 Alembic 管理增量迁移。
