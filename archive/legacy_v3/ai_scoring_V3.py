class AIStrategyScorer:
    def __init__(self):
        self.weights = {"return":0.3, "win_rate":0.4, "drawdown":0.2, "adapt":0.1}

    def score_strategy(self, st, ai_decision):
        ret_score = min(100, max(0, st.total_return * 100))
        win_score = st.win_rate * 100
        dd_score = 100 - min(100, st.drawdown * 1000)
        adapt = 80 if st.direction == ai_decision["decision"].replace("✅","").replace("🟢","").replace("🔴","").strip() else 40
        final = (ret_score*self.weights["return"] +
                 win_score*self.weights["win_rate"] +
                 dd_score*self.weights["drawdown"] +
                 adapt*self.weights["adapt"])
        st.score = round(final, 2)

    def batch_score(self, strategy_list, ai_decision):
        for s in strategy_list:
            if s.is_active:
                self.score_strategy(s, ai_decision)
        return strategy_list

    def set_direction(self, st, ai_decision):
        d = ai_decision["decision"]
        if "做多" in d:
            st.direction = "做多"
        elif "做空" in d:
            st.direction = "做空"
        else:
            st.direction = "观望"