class AlertSystem:
    def __init__(self):
        self.history = []

    def alert_evolution(self, old, new):
        msg = f"[进化] 淘汰 {old.strategy_id}:{old.name} → 新增 {new.strategy_id}:{new.name} 第{new.generation}代"
        self.history.append(msg)
        print(msg)

    def alert_best(self, old_best, new_best):
        if not old_best or old_best.strategy_id != new_best.strategy_id:
            msg = f"[选优] 执行 {new_best.strategy_id}:{new_best.name} 评分:{new_best.score}"
            self.history.append(msg)
            print(msg)

    def alert_info(self, msg):
        self.history.append(msg)
        print(msg)

    def latest(self, n=5):
        return self.history[-n:]