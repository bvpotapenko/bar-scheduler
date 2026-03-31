# api/ — public interface

## Conventions

- Every public function takes `data_dir: Path` as its first argument. This is what enables per-user isolation.
- Functions load fresh state from disk on every call. No in-memory caching between calls.
- `__init__.py` is the only public export point. Every new public function must be exported there.

## Module split

| Module | Owns |
|--------|------|
| `_profile.py` | `init_profile`, `get_profile`, `update_profile`, `update_bodyweight`, `update_language` |
| `_exercises.py` | `enable_exercise`, `disable_exercise`, `set_exercise_target`, `set_exercise_days`, `list_exercises`, `get_exercise_info` |
| `_sessions.py` | `log_session`, `delete_session`, `get_history` |
| `_plan.py` | `get_plan`, `refresh_plan`, `set_plan_start_date`, `get_plan_weeks`, `set_plan_weeks` |
| `_analysis.py` | `get_training_status`, `get_onerepmax_data`, `get_volume_data`, `get_progress_data`, `get_overtraining_status`, `get_goal_metrics` |
| `_equipment.py` | `update_equipment`, `get_current_equipment`, `check_band_progression`, `compute_leff`, `get_equipment_catalog` |
| `_utils.py` | `get_data_dir`, `parse_sets_string`, `training_max_from_baseline` |
| `_common.py` | Shared helpers: store access, timeline conversion, exception definitions |
| `types.py` | `SessionInput`, `SetInput`, `SessionType` — input validation schemas |

## Adding a public function

1. Add to the matching `_*.py` module
2. Export in `__init__.py`
3. Document in `docs/api_info.md`
4. If a new input type is needed, add it to `types.py`
5. Add a test in `tests/test_api.py`

## Shared utilities

Use `_common.py` for store access and timeline helpers — don't duplicate. Exceptions are also defined there; don't create new exception classes without exporting them from `__init__.py`.
