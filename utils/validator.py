"""工具模块 - 数据验证
统一校验配置、参数的合法性，避免无效数据进入系统
"""
from typing import Dict, Any
from utils.logger import get_logger
from utils.exceptions import ConfigError

logger = get_logger("utils.validator")

def validate_preferences(prefs: Dict[str, Any]) -> None:
    """校验用户偏好配置的合法性
    输入：Dict - 用户配置字典
    异常：ConfigError - 配置不合法时抛出
    """
    # 校验止损比例（0.1-50%）
    stop_loss = prefs.get("max_stop_loss_pct", 2.0)
    if not isinstance(stop_loss, (int, float)) or stop_loss < 0.1 or stop_loss > 50:
        raise ConfigError(f"止损比例不合法：{stop_loss}%（必须0.1-50之间）")
    
    # 校验杠杆倍数（1-100倍）
    leverage = prefs.get("preferred_leverage", 1)
    if not isinstance(leverage, int) or leverage < 1 or leverage > 100:
        raise ConfigError(f"杠杆倍数不合法：{leverage}x（必须1-100之间）")
    
    # 校验风险等级（只能是low/medium/high）
    risk_level = prefs.get("risk_level", "medium")
    if risk_level not in ["low", "medium", "high"]:
        raise ConfigError(f"风险等级不合法：{risk_level}（只能是low/medium/high）")
    
    # 校验交易风格（只能是scalp/day/swing/long）
    trade_style = prefs.get("trade_style", "swing")
    if trade_style not in ["scalp", "day", "swing", "long"]:
        raise ConfigError(f"交易风格不合法：{trade_style}（只能是scalp/day/swing/long）")
    
    logger.info("配置校验通过")

def validate_price(price: float) -> None:
    """校验价格合法性
    输入：float - BTC价格
    异常：DataFetchError - 价格不合法时抛出
    """
    if not isinstance(price, (int, float)) or price <= 0:
        raise ConfigError(f"价格不合法：{price}（必须是正数）")
