# evolution_core.py - 全自动进化 + 网页实时报表
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_BJ = ZoneInfo("Asia/Shanghai")
from typing import Any, Dict, List, Optional, Tuple

from utils.trade_exit_rules import first_exit_tick, first_exit_tick_post_tp1

# 与 live_trading 等处一致：始终绑定本文件所在目录下的 trade_memory.json，避免受进程 CWD 影响读到错误/陈旧数据
_REPO_DIR = Path(__file__).resolve().parent
_DEFAULT_TRADE_MEMORY = _REPO_DIR / "trade_memory.json"


def _experiment_tp1_partial_applies(t: Dict[str, Any]) -> bool:
    """仅带 symbol 的实验轨开仓启用 TP1 部分锁定（legacy 无 symbol 单保持原单次平仓）。"""
    if os.environ.get("LONGXIA_EXPERIMENT_TP1_PARTIAL", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return bool(str(t.get("symbol") or "").strip())


def _arm_tp1_partial(t: Dict[str, Any], hit: Tuple[Any, ...]) -> None:
    """命中 TP1：锁定部分盈亏（名义），止损抬到保本±缓冲；仓位仍一笔 open_trades，后续用 post_tp1 规则平仓。"""
    pr = float(os.environ.get("LONGXIA_EXPERIMENT_PARTIAL_RATIO", "0.5"))
    pr = max(0.05, min(pr, 0.95))
    be_buf = float(os.environ.get("LONGXIA_EXPERIMENT_BE_BUFFER_PCT", "0.0002"))
    entry = float(t["entry"])
    d = str(t.get("direction") or "")
    if d == "模拟入场":
        d = "做多"
    if d == "做多":
        t["sl"] = entry * (1.0 + be_buf)
    elif d == "做空":
        t["sl"] = entry * (1.0 - be_buf)
    t["experiment_tp1_done"] = True
    t["experiment_partial_ratio"] = round(pr, 4)
    t["experiment_locked_pct"] = round(float(hit[1]) * pr, 4)


def _blended_profit_pct(t: Dict[str, Any], hit: Tuple[Any, ...]) -> float:
    """剩余仓位按全仓口径的 hit[1]，与已锁定部分加权合成最终盈亏%（记一笔平仓）。"""
    pr = float(t.get("experiment_partial_ratio") or 0.5)
    locked = float(t.get("experiment_locked_pct") or 0.0)
    p_full = float(hit[1])
    return round(locked + (1.0 - pr) * p_full, 2)


def _close_reason_for_hit(trade: Dict[str, Any], bracket: str) -> str:
    b = str(bracket or "").strip()
    if not b:
        return "—"
    if trade.get("experiment_tp1_done") and b == "sl":
        return "BE"
    return {"sl": "SL", "tp1": "TP1", "tp2": "TP2", "tp3": "TP3"}.get(b, b.upper())


class EvolutionConfig:
    SL_MIN = 0.2
    SL_MAX = 0.5
    TP_MIN = 0.5
    TP_MAX = 1.5
    MEMORY_FILE = _DEFAULT_TRADE_MEMORY

class TradeMemory:
    def __init__(self):
        self.file = Path(EvolutionConfig.MEMORY_FILE)
        self._envelope: Optional[Dict[str, Any]] = None
        self.data = self._load()
        self.open_trades = []

    def _load(self):
        self._envelope = None
        if not self.file.exists():
            self._save([])
            return []
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
            if isinstance(raw, dict) and isinstance(raw.get("trades"), list):
                self._envelope = {k: v for k, v in raw.items() if k != "trades"}
                return [x for x in raw["trades"] if isinstance(x, dict)]
            return []
        except Exception:
            return []

    def _save(self, data=None):
        try:
            from utils.trade_memory_autobak import maybe_backup_trade_memory

            maybe_backup_trade_memory(self.file)
        except Exception:
            pass
        target = data if data is not None else self.data
        with open(self.file, "w", encoding="utf-8") as f:
            if self._envelope is not None:
                json.dump({**self._envelope, "trades": target}, f, ensure_ascii=False, indent=2)
            else:
                json.dump(target, f, ensure_ascii=False, indent=2)

    def add_open_trade(
        self,
        direction,
        entry,
        sl,
        tp1,
        tp2,
        tp3,
        symbol: str = "",
        **meta: Any,
    ) -> None:
        """开仓；direction 仅接受 做多/做空。带 symbol 时每币种最多一笔未平仓（实验轨多币种）。
        meta：levels_source、markov_template、斐价位等，平仓写入 trade_memory 时一并落盘。"""
        if direction not in ("做多", "做空"):
            return
        sym = str(symbol or "").strip()
        if sym:
            for t in self.open_trades:
                if str(t.get("symbol") or "").strip() == sym:
                    return
        else:
            for t in self.open_trades:
                if str(t.get("symbol") or "").strip():
                    continue
                if abs(float(t["entry"]) - float(entry)) < 1:
                    return
        rec: Dict[str, Any] = {
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "symbol": sym,
            "entry_time": time.time(),
        }
        for k, v in meta.items():
            if v is not None and k not in rec:
                rec[k] = v
        self.open_trades.append(rec)

    def check_close_trade(
        self, current_price, symbol: Optional[str] = None
    ) -> Optional[Tuple[float, str]]:
        """symbol 为 None 时仅撮合「无 symbol」的遗留单；否则只撮合该币种。返回 (盈亏%, 方向)。"""
        profit = None
        idx = None
        hit_bracket: Optional[str] = None
        filt = None if symbol is None else str(symbol).strip()
        for i, t in enumerate(self.open_trades):
            ts = str(t.get("symbol") or "").strip()
            if filt is None:
                if ts != "":
                    continue
            elif ts != filt:
                continue
            d = t["direction"]
            p = float(current_price)
            if t.get("experiment_tp1_done"):
                hit = first_exit_tick_post_tp1(
                    d,
                    float(t["entry"]),
                    float(t["sl"]),
                    float(t["tp2"]),
                    float(t["tp3"]),
                    p,
                )
                if hit is None:
                    continue
                profit = _blended_profit_pct(t, hit)
                hit_bracket = str(hit[0])
                idx = i
                break
            hit = first_exit_tick(
                d,
                float(t["entry"]),
                float(t["sl"]),
                float(t["tp1"]),
                float(t["tp2"]),
                float(t["tp3"]),
                p,
            )
            if hit is not None:
                if (
                    str(hit[0]) == "tp1"
                    and _experiment_tp1_partial_applies(t)
                ):
                    _arm_tp1_partial(t, hit)
                    return None
                profit = float(hit[1])
                hit_bracket = str(hit[0])
                idx = i
                break
        if idx is not None and profit is not None:
            trade = self.open_trades.pop(idx)
            direction = str(trade.get("direction") or "做多")
            self.save_record(trade, profit, current_price, hit_bracket=hit_bracket)
            return (profit, direction)
        return None

    def save_record(self, trade, profit, close_price, hit_bracket: Optional[str] = None):
        today = datetime.now(_BJ).strftime("%Y-%m-%d")
        entry_u = datetime.fromtimestamp(trade["entry_time"], tz=timezone.utc)
        close_u = datetime.now(timezone.utc)
        sym = str(trade.get("symbol") or "").strip()
        rp = 6 if sym else 2
        cr = _close_reason_for_hit(trade, str(hit_bracket or ""))
        record = {
            "date": today,
            "entry_time": entry_u.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close_time": close_u.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "direction": trade["direction"],
            "entry": round(trade["entry"], rp),
            "sl": round(trade["sl"], rp),
            "tp1": round(trade["tp1"], rp),
            "tp2": round(trade["tp2"], rp),
            "tp3": round(trade["tp3"], rp),
            "close": round(close_price, rp),
            "profit": round(profit, 2),
            "close_reason": cr,
        }
        if trade.get("experiment_tp1_done"):
            record["tp1_hit"] = True
            record["partial_ratio"] = trade.get("experiment_partial_ratio")
            record["partial_locked_pct"] = trade.get("experiment_locked_pct")
        if sym:
            record["symbol"] = sym
        for k in (
            "levels_source",
            "markov_template",
            "regime",
            "markov_regime_line",
            "experiment_markov_template_enabled",
            "fib_0_618",
            "fib_1_618_up",
            "fib_1_618_down",
        ):
            if k in trade and trade[k] is not None:
                v = trade[k]
                if isinstance(v, float):
                    record[k] = round(v, rp)
                else:
                    record[k] = v
        self.data.append(record)
        self._save()

    def append_virtual_signal_record(self, symbol: str, entry: float, last_sig: int) -> None:
        """V3.16.2：state 今日信号计数增加时写入一条虚拟入场（不计入胜率统计）。"""
        today = datetime.now(_BJ).strftime("%Y-%m-%d")
        entry = float(entry)
        direction = "做多" if last_sig > 0 else ("做空" if last_sig < 0 else "模拟入场")
        if direction == "做多":
            sl_v = round(entry * (1 - 0.003), 6)
            tp1_v = round(entry * (1 + 0.0012), 6)
            tp2_v = round(entry * (1 + 0.0045), 6)
            tp3_v = round(entry * (1 + 0.0045), 6)
        elif direction == "做空":
            sl_v = round(entry * (1 + 0.003), 6)
            tp1_v = round(entry * (1 - 0.0012), 6)
            tp2_v = round(entry * (1 - 0.0045), 6)
            tp3_v = round(entry * (1 - 0.0045), 6)
        else:
            sl_v = round(entry * (1 - 0.003), 6)
            tp1_v = round(entry * (1 + 0.0012), 6)
            tp2_v = round(entry * (1 + 0.0045), 6)
            tp3_v = round(entry * (1 + 0.0045), 6)
        record = {
            "date": today,
            "entry_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close_time": "—",
            "direction": direction,
            "entry": round(entry, 6),
            "sl": sl_v,
            "tp1": tp1_v,
            "tp2": tp2_v,
            "tp3": tp3_v,
            "close": None,
            "profit": None,
            "virtual_signal": True,
            "symbol": symbol,
        }
        self.data.append(record)
        self._save()

class StrategyAnalyzer:
    def __init__(self, memory):
        self.m = memory

    def get_report(self):
        today = datetime.now(_BJ).strftime("%Y-%m-%d")
        rows = [r for r in self.m.data if isinstance(r, dict)]
        records = [
            r
            for r in rows
            if r.get("profit") is not None and not r.get("virtual_signal")
        ]
        virtual_today = [
            r
            for r in rows
            if r.get("virtual_signal") and r.get("date") == today
        ]
        day_closed = [r for r in records if r.get("date") == today]

        if not records and not virtual_today:
            return {"status": "waiting"}

        t_total = len(records)
        t_win = len([r for r in records if r["profit"] > 0])
        t_loss = t_total - t_win
        t_winr = round(t_win / t_total * 100, 2) if t_total else 0

        d_total = len(day_closed)
        d_win = len([r for r in day_closed if r["profit"] > 0])
        d_loss = d_total - d_win
        d_winr = round(d_win / d_total * 100, 2) if d_total else 0

        longs = [r for r in records if r["direction"] == "做多"]
        shorts = [r for r in records if r["direction"] == "做空"]
        l_win = len([r for r in longs if r["profit"] > 0])
        s_win = len([r for r in shorts if r["profit"] > 0])
        l_winr = round(l_win / len(longs) * 100, 2) if longs else 0
        s_winr = round(s_win / len(shorts) * 100, 2) if shorts else 0

        def _tkey(x: Dict) -> str:
            return str(x.get("entry_time") or "")

        day_orders = sorted(day_closed + virtual_today, key=_tkey)

        return {
            "总交易": t_total,
            "总赢": t_win,
            "总亏": t_loss,
            "总胜率": t_winr,
            "今日交易": d_total,
            "今日模拟入场": len(virtual_today),
            "今日赢": d_win,
            "今日亏": d_loss,
            "今日胜率": d_winr,
            "做多胜率": l_winr,
            "做空胜率": s_winr,
            "今日订单": day_orders,
        }

class AIAutoEvolution:
    def __init__(self):
        self.memory = TradeMemory()
        self.analyzer = StrategyAnalyzer(self.memory)

    def record(
        self,
        direction,
        entry,
        sl,
        tp1,
        tp2,
        tp3,
        *,
        symbol: str = "",
        **meta: Any,
    ):
        self.memory.add_open_trade(
            direction, entry, sl, tp1, tp2, tp3, symbol=symbol, **meta
        )

    def tick(self, price, symbol: Optional[str] = None) -> Optional[Tuple[float, str]]:
        return self.memory.check_close_trade(price, symbol)

    def report(self):
        return self.analyzer.get_report()

    def show_dashboard(self):
        rep = self.report()
        print("-" * 82)
        print("📊 实时战绩统计")
        print("-" * 82)
        print(f"总胜率：{rep['总胜率']}% | 总交易：{rep['总交易']} 赢：{rep['总赢']} 亏：{rep['总亏']}")
        print(f"今日胜率：{rep['今日胜率']}% | 今日交易：{rep['今日交易']} 赢：{rep['今日赢']} 亏：{rep['今日亏']}")
        print(f"做多胜率：{rep['做多胜率']}% | 做空胜率：{rep['做空胜率']}%")
        print("-" * 82)
        print("📋 今日订单详情")
        print("-" * 82)
        if not rep["今日订单"]:
            print("暂无今日订单")
        else:
            for idx, o in enumerate(rep["今日订单"][-10:]):
                p = o["profit"]
                res = "✅盈利" if p > 0 else "❌亏损"
                p_str = f"+{p}" if p > 0 else f"{p}"
                sym = f"{o.get('symbol')}|" if o.get("symbol") else ""
                print(
                    f"#{idx+1} | {sym}{o['entry_time']} | {o['direction']} | "
                    f"入场:{o['entry']} | 止损:{o['sl']} | 平仓:{o['close']} | {res} {p_str}%"
                )
        print("-" * 82 + "\n")

ai_evo = AIAutoEvolution()
