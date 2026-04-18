"""工具模块 - 自定义异常+统一异常处理
封装系统专属异常，方便定位问题
"""
from utils.logger import get_logger

logger = get_logger("utils.exceptions")

# 自定义异常（按功能分类）
class ConfigError(Exception):
    """配置相关异常"""
    pass

class DataFetchError(Exception):
    """数据获取相关异常"""
    pass

class TradeRecordError(Exception):
    """交易记录相关异常"""
    pass

class AIDecisionError(Exception):
    """AI决策相关异常"""
    pass

# 统一异常处理装饰器（其他模块直接用）
def catch_exception(exception_type: Exception = Exception):
    """异常捕获装饰器
    输入：Exception - 要捕获的异常类型
    功能：自动记录异常日志，返回友好提示
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_type as e:
                logger.error(f"函数{func.__name__}执行失败：{str(e)}", exc_info=True)
                raise  # 抛出异常，让上层处理
            except Exception as e:
                logger.error(f"函数{func.__name__}未知错误：{str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator
