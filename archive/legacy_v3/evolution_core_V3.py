from strategy_genes_V3 import mutate_from_best

class EvolutionCore:
    def __init__(self, alert):
        self.alert = alert
        self.evolution_cycle = 0

    def get_sorted_active(self, strategies):
        return sorted([s for s in strategies if s.is_active], key=lambda x:x.score, reverse=True)

    def run_evolution(self, strategies):
        self.evolution_cycle +=1
        active = self.get_sorted_active(strategies)
        if len(active) <1:
            return strategies
        best = active[0]
        weakest = active[-1]
        weakest.is_active = False
        new_id = max([s.strategy_id for s in strategies]) +1
        new_st = mutate_from_best(best, new_id)
        strategies.append(new_st)
        self.alert.alert_evolution(weakest, new_st)
        return strategies

    def need_evolve(self, strategies, cycle):
        active = self.get_sorted_active(strategies)
        if not active:
            return True
        min_score = min([s.score for s in active])
        return cycle %20 ==0 or min_score <30