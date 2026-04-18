"""工具模块 - 日志封装
统一管理系统日志，所有模块都用这个日志工具，避免重复写print
"""
import logging
import os
from datetime import datetime

# 创建日志目录
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 配置日志格式
LOG_FILE = os.path.join(LOG_DIR, f"openclaw_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),  # 保存到文件
        logging.StreamHandler()  # 输出到终端
    ]
)

# 创建全局日志对象
def get_logger(name: str) -> logging.Logger:
    """获取日志对象
    输入：str - 模块名（如"config.settings"）
    返回：logging.Logger - 日志对象
    """
    return logging.getLogger(name)
