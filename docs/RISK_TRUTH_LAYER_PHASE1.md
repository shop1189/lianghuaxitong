# Risk Truth Layer Phase-1 (observe-only)

## Goal

Build a single capital truth input and provide risk advisory outputs without blocking existing open/close execution.

## Mode

- Fixed mode: `observe`
- No hard gate for order flow
- Only add fields/logs

## Data Source

- File: `state/risk_capital_snapshot.json`
- Required fields:
  - `equity_usdt`
  - `free_margin_usdt`
  - `open_positions` (array)
  - `updated_at` (unix epoch seconds)
  - `source` (currently `manual`)

TTL validation:

- `LONGXIA_RISK_CAPITAL_TTL_SEC` (default `600`)
- If stale/missing/invalid -> warning reason codes only

## Formulas

Position sizing (`risk/position_sizer.py`):

- `stop_pct = abs(entry - stop) / entry`
- `effective_stop_pct = stop_pct + fee_slippage_buffer_pct`
- `risk_usdt = equity_usdt * risk_per_trade_pct`
- `suggested_notional_usdt = risk_usdt / effective_stop_pct`

Leverage recommendation (`risk/leverage_policy.py`):

- Input: `symbol`, optional `atr_pct`, optional `liquidity_tier`
- Output:
  - `recommended_leverage`
  - `max_allowed_leverage`
  - `reason`

Portfolio warning (`risk/portfolio_guard.py`):

- Input: current open positions + new advisory position
- Warning-only checks:
  - same direction exposure threshold
  - portfolio total risk threshold
  - day stop threshold

## Default Params (Phase-1 fixed)

- `LONGXIA_RISK_LAYER_MODE=observe`
- `LONGXIA_RISK_PER_TRADE_PCT=0.005`
- `LONGXIA_RISK_MAX_DIRECTION_PCT=0.015`
- `LONGXIA_RISK_MAX_PORTFOLIO_PCT=0.03`
- `LONGXIA_RISK_DAY_STOP_PCT=-0.015`
- `LONGXIA_RISK_CAPITAL_TTL_SEC=600`
- `LONGXIA_RISK_FEE_SLIPPAGE_BUFFER_PCT=0.001`

## Integration Point

- `live_trading.get_v313_decision_snapshot(...)`
- Add step: compute `risk_advisory`
- Add bundle: `risk_advisory_bundle` for all board profiles (`main`, `experiment`, `teacher_boost`, `teacher_combat`)
- Write `risk_advisory` into snapshot (`km`) only
- Do not alter original signal/open/close execution path

## Audit Log

File: `logs/risk_decisions.jsonl` (append only)

Each line contains at least:

- `ts`, `symbol`, `side`
- `equity_usdt`, `free_margin_usdt`
- `entry`, `stop`, `stop_pct`, `effective_stop_pct`
- `risk_usdt`, `suggested_notional_usdt`
- `recommended_leverage`, `max_allowed_leverage`
- `warnings[]`
- `mode=observe`

## Run

1. Maintain `state/risk_capital_snapshot.json`
2. Start existing service as usual
   - **推荐端口分工（本机并行）**：
     - **18080**：Phase-1 风险真理层 / Web 验收专用（`python3 main.py` 默认端口；也可用 `LONGXIA_HTTP_PORT` / `PORT` 覆盖）。便捷 env：`config/http_port_phase1_web.env`
     - **8080**：回测 / 快轨等并行任务专用（例如 `config/exp_fastlane_*.env` 里 `LONGXIA_HTTP_PORT=8080`）。便捷 env：`config/http_port_backtest.env`
3. Visit `/decision` or any flow that triggers decision snapshot
4. Check `logs/risk_decisions.jsonl`

## Rollback

1. Remove risk advisory injection in `live_trading.py`
2. Keep risk files as dormant modules
3. Existing order execution path remains unchanged
