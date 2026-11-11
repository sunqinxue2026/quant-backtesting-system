CREATE DATABASE IF NOT EXISTS quant_db DEFAULT CHARACTER SET utf8mb4;
USE quant_db;

-- SQLAlchemy Base.metadata.create_all 会创建以下七张表：
-- stock_basic, stock_daily, strategy_config, backtest_task,
-- backtest_order, backtest_trade, backtest_result
-- 生产环境建议通过 Alembic 或受控迁移执行 DDL。
