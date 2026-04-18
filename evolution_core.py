# evolution_core.py - 全自动进化 + 网页实时报表
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_BJ = ZoneInfo("Asia/Shanghai")
from typing import Any, Dict, List, Optional

# 与 live_trading 等处一致：始终绑定本文件所在目录下的 trade_memory.json，避免受进程 CWD 影响读到错误/陈旧数据
_REPO_DIR = Path(__file__).resolve().parent
_DEFAULT_TRADE_MEMORY = _REPO_DIR / "trade_memory.json"

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
        target = data if data is not None else self.data
        with open(self.file, "w", encoding="utf-8") as f:
            if self._envelope is not None:
                json.dump({**self._envelope, "trades": target}, f, ensure_ascii=False, indent=2)
            else:
                json.dump(target, f, ensure_ascii=False, indent=2)

    def add_open_trade(self, direction, entry, sl, tp1, tp2, tp3):
        for t in self.open_trades:
            if abs(t["entry"] - entry) < 1:
                return
        self.open_trades.append({
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "entry_time": time.time()
        })

    def check_close_trade(self, current_price):
        profit = None
        idx = None
        for i, t in enumerate(self.open_trades):
            d, entry, sl, tp1, tp2, tp3 = t["direction"], t["entry"], t["sl"], t["tp1"], t["tp2"], t["tp3"]
            if d == "做多":
                if current_price <= sl:
                    profit = round((sl / entry - 1) * 100, 2)
                    idx = i
                elif current_price >= tp3:
                    profit = round((tp3 / entry - 1) * 100, 2)
                    idx = i
                elif current_price >= tp2:
                    profit = round((tp2 / entry - 1) * 100, 2)
                    idx = i
                elif current_price >= tp1:
                    profit = round((tp1 / entry - 1) * 100, 2)
                    idx = i
            elif d == "做空":
                if current_price >= sl:
                    profit = round((entry - sl) / entry * 100, 2)
                    idx = i
                elif current_price <= tp3:
                    profit = round((entry - tp3) / entry * 100, 2)
                    idx = i
                elif current_price <= tp2:
                    profit = round((entry - tp2) / entry * 100, 2)
                    idx = i
                elif current_price <= tp1:
                    profit = round((entry - tp1) / entry * 100, 2)
                    idx = i
        if idx is not None and profit is not None:
            trade = self.open_trades.pop(idx)
            self.save_record(trade, profit, current_price)
            return profit
        return None

    def save_record(self, trade, profit, close_price):
        today = datetime.now(_BJ).strftime("%Y-%m-%d")
        entry_u = datetime.fromtimestamp(trade["entry_time"], tz=timezone.utc)
        close_u = datetime.now(timezone.utc)
        record = {
            "date": today,
            "entry_time": entry_u.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close_time": close_u.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "direction": trade["direction"],
            "entry": round(trade["entry"], 2),
            "sl": round(trade["sl"], 2),
            "tp1": round(trade["tp1"], 2),
            "tp2": round(trade["tp2"], 2),
            "tp3": round(trade["tp3"], 2),
            "close": round(close_price, 2),
            "profit": round(profit, 2)
        }
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

    def record(self, direction, entry, sl, tp1, tp2, tp3):
        self.memory.add_open_trade(direction, entry, sl, tp1, tp2, tp3)

    def tick(self, price):
        self.memory.check_close_trade(price)

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
                print(f"#{idx+1} | {o['entry_time']} | {o['direction']} | 入场:{o['entry']} | 止损:{o['sl']} | 平仓:{o['close']} | {res} {p_str}%")
        print("-" * 82 + "\n")

ai_evo = AIAutoEvolution()
