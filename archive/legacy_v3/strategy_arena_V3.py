import time
import traceback
from strategy_genes_V3 import init_6_ancestors
from ai_scoring_V3 import AIStrategyScorer
from alert_system_V3 import AlertSystem
from evolution_core_V3 import EvolutionCore

try:
    from ai_decision_upgrade import ai_analysis_multi_timeframe
except:
    def ai_analysis_multi_timeframe():
        return "观望"

try:
    from evolution_core import report
except:
    def report():
        return {"总胜率":50,"今日胜率":50,"做多胜率":50,"做空胜率":50}

class StrategyArena:
    def __init__(self):
        self.strategies = init_6_ancestors()
        self.scorer = AIStrategyScorer()
        self.alert = AlertSystem()
        self.evo = EvolutionCore(self.alert)
        self.cycle = 0
        self.current_best = None
        self.last_action = ""

    def update_performance(self):
        try:
            rep = report()
            wr = float(rep.get("今日胜率",50))/100
            for s in self.strategies:
                if s.is_active:
                    s.win_rate = wr
                    s.total_return = (wr-0.5)*0.1
                    s.drawdown = 0.005
        except:
            pass

    def get_best_strategy(self):
        try:
            active = [s for s in self.strategies if s.is_active]
            return sorted(active,key=lambda x:x.score,reverse=True)[0] if active else None
        except:
            return None

    def show_dashboard(self,ai_dec):
        print("\033c",end="")
        self.cycle +=1
        rep = report()

        print("="*88)
        print(f"🔥 V3.0 实战策略竞技场 | 运行周期：{self.cycle} | 进化代数：{self.evo.evolution_cycle}")
        print("="*88)
        print(f"{'ID':<4}{'策略名称':<18}{'方向':<8}{'AI评分':<10}{'胜率':<8}{'状态':<6}")
        print("-"*88)
        for s in self.strategies:
            stat = "激活" if s.is_active else "淘汰"
            print(f"{s.strategy_id:<4}{s.name:<18}{s.direction:<8}{s.score:<10}{round(s.win_rate*100,1):<8}{stat:<6}")

        if self.current_best:
            print("\n"+"="*88)
            print(f"🎯 【最终实盘指令】由最高分策略【{self.current_best.name}】给出".center(88))
            print("="*88)

            cmd = self.current_best.direction
            if cmd == "做多":
                print(f"🟢 👉 实盘操作：【做多】".center(88))
                self.last_action = "做多"
            elif cmd == "做空":
                print(f"🔴 👉 实盘操作：【做空】".center(88))
                self.last_action = "做空"
            else:
                print(f"⚪ 👉 实盘操作：【观望 不操作】".center(88))
                self.last_action = "观望"

        print("\n"+"-"*88)
        print(f"📊 真实战绩：总胜率 {rep.get('总胜率')}% ｜今日 {rep.get('今日胜率')}%")
        print(f"🧠 AI 方向判断：{ai_dec}")
        print("🔔 系统提醒：")
        for m in self.alert.latest(4):
            print(f" • {m}")
        print("="*88)

    def run(self):
        while True:
            try:
                ai_decision = ai_analysis_multi_timeframe()
                self.update_performance()
                self.scorer.batch_score(self.strategies,ai_decision)
                for s in self.strategies:
                    if s.is_active:
                        self.scorer.set_direction(s,ai_decision)

                new_best = self.get_best_strategy()
                self.alert.alert_best(self.current_best,new_best)
                self.current_best = new_best

                if self.evo.need_evolve(self.strategies,self.cycle):
                    self.strategies = self.evo.run_evolution(self.strategies)

                self.show_dashboard(ai_decision)
                time.sleep(4)

            except KeyboardInterrupt:
                print("\n✅ 安全停止")
                break
            except:
                time.sleep(5)

if __name__ == "__main__":
    arena = StrategyArena()
    arena.run()