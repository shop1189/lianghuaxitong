class StrategyGene:
    def __init__(self, strategy_id, name, strategy_type):
        self.strategy_id = strategy_id
        self.name = name
        self.strategy_type = strategy_type
        self.score = 0.0
        self.win_rate = 0.5
        self.total_return = 0.0
        self.drawdown = 0.0
        self.direction = "观望"
        self.is_active = True
        self.generation = 1

    def calc_signal(self, ai_decision):
        if isinstance(ai_decision, dict):
            d = ai_decision.get("decision", "")
        else:
            d = str(ai_decision)
        if "做多" in d:
            return 1
        elif "做空" in d:
            return -1
        else:
            return 0

def init_6_ancestors():
    return [
        StrategyGene(1, "趋势跟随", "trend"),
        StrategyGene(2, "震荡高抛低吸", "range"),
        StrategyGene(3, "高低突破", "breakout"),
        StrategyGene(4, "反转抓底", "reverse"),
        StrategyGene(5, "动量加速", "momentum"),
        StrategyGene(6, "稳健复利", "stable")
    ]

def mutate_from_best(best_strategy, new_id):
    s = StrategyGene(new_id, f"进化版_{best_strategy.name}", best_strategy.strategy_type)
    s.generation = best_strategy.generation + 1
    s.win_rate = best_strategy.win_rate * 0.95
    s.direction = best_strategy.direction
    return s