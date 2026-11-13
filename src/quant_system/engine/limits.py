"""交易数量的持久化边界。"""

# SQLAlchemy Integer 对应各目标数据库均支持的有符号 32 位整数范围。
MAX_ORDER_QUANTITY = 2**31 - 1
