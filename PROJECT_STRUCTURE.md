# Longxia System Project Structure

## Active Mainline (keep using)

Primary runtime chain:

1. `main.py`
2. `web/ui.py`
3. `trade/ai_decision.py`
4. `ai_decision_upgrade.py`
5. `data_upgrade.py`
6. `indicator_upgrade.py`
7. `evolution_core.py`

Supporting modules still used by the active app:

- `config/settings.py`
- `data/fetcher.py`
- `trade/records.py`
- `utils/logger.py`
- `utils/exceptions.py`
- `utils/validator.py`
- `data_feed.py` (currently used by `data/fetcher.py`)

## Archive Layout

Legacy files are moved (not deleted) to `archive/`:

- `archive/legacy_runtime/`: old integrated runtime scripts
- `archive/legacy_v3/`: old V3 arena/evolution scripts
- `archive/legacy_ai_roles/`: old role-based AI wrappers
- `archive/legacy_tests/`: old step-by-step verification scripts
- `archive/legacy_fixes/`: one-off fix scripts
- `archive/legacy_backups/`: saved/backup variants
- `archive/legacy_web/`: old standalone web template/page

## Notes

- No active import paths were changed for the current mainline chain.
- Archive content is kept for rollback/reference only.
