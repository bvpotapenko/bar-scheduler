# bar-scheduler — Claude instructions

## Environment

- Python 3.14, managed with **uv**
- `uv run pytest` — run tests
- `uv sync` / `uv sync --extra dev` — install deps
- Always run `uv run ruff check src tests` **before** `uv run pytest`. Fix any ruff issues first.

## Workflow rules

- **No auto-commits.** Make file changes and stop. Never run `git commit`. The user commits manually.
- **Bug-fix workflow:** confirm bug → write failing test → fix → confirm pass.
- **Backlog:** when skipping something (out of scope, too complex, noticed smell but not fixing it), add it to `backlog.md` in the appropriate section. Never silently drop deferred work.
- **Backward compatibility:** never assume it's needed. Before any API refactor or interface change, ask. If not needed, delete the old interface entirely — no shims, no aliases.
- **FAQ:** when the user asks a functionality/formula/behavior question, add a Q&A entry to `docs/FAQ.md`. FAQ covers active behavior only — not removed features (those go in CHANGELOG only).

## Testing philosophy

Every test must assert at least one specific expected output value (`== 10`, `== [1,2,3]`, `pytest.raises(SpecificError)`). Never write:
- crash-only tests (no assertions, or only `assert result is not None`)
- file-existence checks (`.exists()`)
- key-presence-only checks (`assert "key" in result`)
- isinstance-only checks
- API shape checks via `inspect.signature`

This is a library. We care about correctness of computed values.

## Code style

- Short, focused, elegant code. No god classes or god functions. Cohesive over comprehensive.
- No legacy/compat shims unless explicitly requested. Just change it.
- No `| dict` fallbacks, `# removed` comments, or re-exports for old callers.
- When a function grows complex, split it rather than adding branches.

## Architecture

```
src/bar_scheduler/
  core/
    exercises/    — base.py, loader.py, registry.py (ExerciseDefinition)
    engine/       — config_loader.py
    planner/      — load_calculator.py, adaptation.py, test_session_inserter.py, …
    config.py
  io/
  api/            — _profile.py, _exercises.py, _sessions.py, _plan.py,
                    _analysis.py, _equipment.py, _utils.py, _common.py,
                    types.py (SessionInput, SetInput, SessionType)
exercises/        — pull_up.yaml, dip.yaml, bss.yaml, incline_db_press.yaml
```

All public operations via `from bar_scheduler.api import ...`.

Config source of truth: `src/bar_scheduler/exercises.yaml` (user-overridable via `~/.bar-scheduler/exercises.yaml`).

Storage: JSONL files.

## Key domain facts

- `UserProfile` fields: `height_cm`, `bodyweight_kg`, `exercise_days`, `exercise_targets`, `exercises_enabled`, `language`
- `status.training_max = floor(0.9 × test_max)`
- SESSION_TARGET_REPS: S→5, H→8, E→12, T→6
- `DAY_SPACING["TEST"] = 1` (next session ≥ TEST_date + 2)
- Autoregulation gated at `MIN_SESSIONS_FOR_AUTOREG = 10`
- No `GAMMA_BW`: bodyweight normalization is always linear
- Equipment: `BAND_SET` uses ceiling-snap to declared `available_band_assistance_kg`
- `plan_start_date` stored per-exercise in `profile.json["plan_start_dates"]["<exercise_id>"]`
- `week_number` anchored to first session in history
- Prescription stability invariant: `prescription(D) = f(history date < D, profile)`

## Docs to keep updated

- `CHANGELOG.md` — update on every release
- `docs/features.md` — update after every feature addition or removal
- `docs/FAQ.md` — add Q&A when user asks functionality questions
