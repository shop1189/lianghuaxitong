"""交易记录模块 - 持仓记录、止损检查、反转状态
核心依赖：
- 输入：config.settings（配置）、data.fetcher（价格数据）
- 输出：字典（持仓记录）/字符串（反转状态）/None（无持仓）
"""
import json
import os
import time
import asyncio
from typing import Any, Dict, Optional, Union  # 类型注解
from config.settings import get_preferences  # 导入配置模块
from data.fetcher import get_current_price  # 导入数据模块
from utils.logger import get_logger  # 导入日志工具
from utils.exceptions import TradeRecordError  # 导入自定义异常
from utils.structure_guard import (
    StructureGuardParams,
    block_trend_chase_entry,
    early_exit_recommendation,
)

# 初始化日志
logger = get_logger("trade.records")

def get_entry_record() -> Optional[Dict[str, Union[float, str, int]]]:
    """读取最后一次入场记录
    返回：
        Optional[Dict] - 持仓记录字典（包含entry_price/side/time），无记录返回None
    异常：读取失败返回None，同时记录日志
    """
    try:
        if os.path.exists("last_entry.json"):
            with open("last_entry.json", "r", encoding="utf-8") as f:
                record = json.load(f)
                logger.info("成功读取持仓记录")
                return record
        logger.warning("未找到持仓记录文件")
    except Exception as e:
        logger.error(f"读取入场记录失败：{e}", exc_info=True)
    return None

def save_entry_record(price: float, side: str = "LONG") -> Dict[str, Union[float, str, int]]:
    """保存入场记录
    输入：
        price: float - 入场价格（必须>0）
        side: str - 交易方向（默认LONG，可选SHORT）
    返回：
        Dict - 保存的持仓记录字典
    异常：保存失败抛出TradeRecordError
    """
    # 基础校验
    if price <= 0:
        raise TradeRecordError(f"入场价格不合法：{price}（必须>0）")
    if side not in ["LONG", "SHORT"]:
        raise TradeRecordError(f"交易方向不合法：{side}（只能是LONG/SHORT）")
    
    entry = {
        "entry_price": price,
        "side": side,
        "time": time.time()
    }
    try:
        with open("last_entry.json", "w", encoding="utf-8") as f:
            json.dump(entry, f)
        logger.info(f"成功保存持仓记录：{side} @ ${price:.2f}")
        return entry
    except Exception as e:
        logger.error(f"保存入场记录失败：{e}", exc_info=True)
        raise TradeRecordError(f"保存持仓记录失败：{str(e)}")

def get_reversal_status() -> str:
    """检查反转警报状态
    返回：
        str - 反转状态（"警报"/"正常"）
    异常：读取日志失败返回"正常"，同时记录日志
    """
    try:
        if os.path.exists("instruction.log"):
            with open("instruction.log", "r", encoding="utf-8") as f:
                # 只看最后50行，避免读取整个大文件
                lines = f.readlines()
                for line in reversed(lines[-50:] if lines else []):
                    if "AI_ALERT" in line or "立即平仓" in line:
                        logger.warning("检测到反转警报")
                        return "警报"
        logger.info("反转状态检查：正常")
    except Exception as e:
        logger.error(f"检查反转状态失败：{e}", exc_info=True)
    return "正常"

def structure_early_exit_hint(
    open_side_cn: str,
    decision_snapshot: Dict[str, Any],
    unrealized_pnl_pct: Optional[float],
    *,
    experiment_track: bool = True,
    guard_params: Optional[StructureGuardParams] = None,
) -> Optional[str]:
    """
    持仓管理用：当决策快照显示深回调/反转压力时，返回非 None 的简短原因码（供上层写 close_reason）。
    open_side_cn: 做多 / 做空（与 trade_memory 一致）。
    """
    exit_now, reason = early_exit_recommendation(
        open_side_cn,
        decision_snapshot,
        unrealized_pnl_pct,
        guard_params,
        experiment_track=experiment_track,
    )
    return reason if exit_now else None


def structure_entry_blocked(
    want_side_cn: str,
    decision_snapshot: Dict[str, Any],
    *,
    experiment_track: bool = True,
    guard_params: Optional[StructureGuardParams] = None,
) -> Optional[str]:
    """
    开仓前用：若返回非 None，则为拦截原因码（不应再追趋势开 want_side_cn）。
    """
    blocked, reason = block_trend_chase_entry(
        want_side_cn,
        decision_snapshot,
        guard_params,
        experiment_track=experiment_track,
    )
    return reason if blocked else None


async def check_reversal() -> Optional[str]:
    """异步检查是否触发止损（反转）
    返回：
        Optional[str] - 触发止损返回"亏损 X.XX%"，未触发返回None
    异常：计算失败返回None，同时记录日志
    """
    entry = get_entry_record()
    if not entry:
        logger.info("无持仓记录，跳过止损检查")
        return None
    
    entry_price = entry.get("entry_price", 0)
    side = entry.get("side", "LONG")
    current_price = get_current_price()
    prefs = get_preferences()
    max_loss = prefs.get("max_stop_loss_pct", 2.0)
    
    # 基础校验
    if entry_price == 0 or current_price == 0:
        logger.error(f"价格数据异常：入场价={entry_price}，当前价={current_price}")
        return None
    
    # 计算盈亏百分比
    try:
        if side == "LONG":
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100
        
        if pnl_pct < -max_loss:
            loss_msg = f"亏损 {pnl_pct:.2f}%"
            logger.warning(f"触发止损：{loss_msg}")
            return loss_msg
        
        logger.info(f"止损检查：盈亏{pnl_pct:.2f}%，未触发止损（最大允许亏损{max_loss}%）")
        return None
    except Exception as e:
        logger.error(f"计算盈亏百分比失败：{e}", exc_info=True)
        return None
