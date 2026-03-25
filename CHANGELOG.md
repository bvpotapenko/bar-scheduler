# Changelog

All notable changes to bar-scheduler are documented here.

---

## [Unreleased]

### Added

- **EBR metrics — user-facing volume, capability, and progress system** -- replaces the
  internal Banister load in the public API with three distinct, interpretable metrics:
  - **`get_ebr_data(data_dir, exercise_id, weeks_ahead=4) -> dict`** — per-session
    EBR (Equivalent Bodyweight Reps) for history and the upcoming plan. Each entry has
    `{"date", "session_type", "ebr", "kg_eq"}`. Formula:
    `EBR_set = reps × (L_eff/BW)^EBR_ALPHA × rest_penalty`. See
    `docs/performance-formulas.md`.
  - **`get_goal_progress(data_dir, exercise_id) -> dict`** — current strength capability
    and nonlinear progress toward the set goal. Key fields: `max_reps_at_goal` (predicted
    reps at goal weight right now), `progress_pct` (0–100, log-based nonlinear scale),
    `difficulty_ratio` (EBR_goal / EBR_cap — how much harder the goal is vs. now).
  - **`compute_set_ebr(data_dir, exercise_id, reps, added_weight_kg=0.0, *, rest_seconds=180,
    bodyweight_kg=None) -> float`** — EBR for a single hypothetical set. Useful for
    comparing a goal scenario against historical session EBRs.
- **EBR config constants** in `exercises.yaml` (section `ebr_metric`): `EBR_ALPHA=1.6`,
  `REST_TAU=90.0`, `REST_RHO=0.25`, `EBR_BASE=1.0`. User-overridable.
- **`docs/performance-formulas.md`** — formula reference with worked examples for all
  three EBR metrics.
- **`core/ebr.py`** — pure EBR computation functions (no I/O).

### Removed

- **`get_load_data()`** -- replaced by `get_ebr_data()`. The internal Banister
  fitness-fatigue model is unchanged; only the public API surface changes.
- **`compute_session_load()`** -- replaced by `compute_set_ebr()`.
- **Dual-dumbbell weight expansion for BSS** -- when `available_weights_kg` is set for BSS, the planner now expands the stored list of individual dumbbell weights into all achievable totals (single DB + all same/mixed pairs) before snapping the prescription. Example: `[8, 10, 16]` → `[8, 10, 16, 18, 20, 24, 26, 32]`. A prescription of 22 kg snaps to 20 kg (10+10) rather than 16 kg. The user decides how to split the total across their hands — the planner only prescribes the total.
- **`dual_dumbbell` flag on `ExerciseDefinition`** -- new boolean field (default `False`). Set to `true` in `bss.yaml`. Can be set in user-override YAML for custom exercises that also use two dumbbells.

---

## [0.5.1] -- 2026-03-25

### Added

- **Incline Dumbbell Press** (`incline_db_press`) -- fourth exercise in the registry.
  External-load only (`bw_fraction=0.0`); weight logged **per-hand** (single dumbbell).
  No variant rotation (user chooses comfortable grip/angle). TEST frequency every 4 weeks.
  Equipment: adjustable bench + dumbbells.
- **`available_weights_kg` in `EquipmentState`** -- per-exercise list of discrete dumbbell
  (or plate) weights stored in the user's profile. Different exercises can have different
  weight sets (e.g. `incline_db_press` at the gym, `bss` at home). When non-empty, the
  planner **floor-snaps** all weight prescriptions to the largest available weight ≤ the
  computed ideal -- no fractional or unavailable weights are ever prescribed. Empty list
  (default) preserves the previous 0.5 kg rounding behaviour.
- **`available_weights_kg` parameter in `update_equipment()`** -- set or clear discrete
  weight options per exercise. `None` (default) inherits the value from the previous
  equipment entry; `[]` reverts to continuous 0.5 kg rounding.

---

## [0.5.0] -- 2026-03-24

### Breaking changes

- **Import path changed** -- `from bar_scheduler.api.api import ...` is gone. New path: `from bar_scheduler.api import ...`. The old `api/api.py` module has been deleted and replaced by focused submodules (`_profile.py`, `_exercises.py`, `_sessions.py`, `_plan.py`, `_analysis.py`, `_equipment.py`, `_utils.py`).
- **`rest_preference` removed from `UserProfile`** -- field, serialization, and all API parameters (`init_profile`, `update_profile`) removed. Dead code — never affected planning.
- **`injury_notes` removed from `UserProfile`** -- field, serialization, and API parameter (`update_profile`) removed. Dead code — never affected planning.
- **`GAMMA_BW` removed from `core/config.py`** -- bodyweight normalization is always linear (exponent 1.0). The `bodyweight_normalization` YAML section is also gone. `bodyweight_normalized_reps()` in `metrics.py` simplified to `reps * l_rel`.
- **`DAY_SPACING["TEST"]` changed 2 → 1** -- 1 rest day after a TEST session (next session at TEST_date + 2). Previously the value was defined but never enforced.
- **`build_fitness_fatigue_state()` return type changed** -- now returns `tuple[FitnessFatigueState, list[tuple[str, float]]]`. Second element is per-session `(date, load)` pairs. Callers must unpack: `ff_state, _ = build_fitness_fatigue_state(...)`.

### Added

- **`from bar_scheduler.api.types import SessionType, SetInput, SessionInput`** -- typed input primitives for session logging. `SessionInput` validates date format, session type, and bodyweight. `SetInput` validates reps, rest, and weight.
- **TEST session recovery spacing enforced** -- `_insert_test_sessions()` now calls `_enforce_test_spacing()`, which pushes plan sessions that are too close to a TEST (historical or in-plan) forward by the required gap.
- **Goal-driven progression** -- `set_exercise_target(data_dir, exercise_id, reps=N)` or `reps=N, weight_kg=W` now directly wires into `plan_engine.py`:
  - Reps-only goal: TM progression stops at `goal_reps`.
  - Weighted goal: TM continues past `goal_reps` (at minimum `DELTA_PROGRESSION_MIN` reps/week) until the Epley-derived weight prescription at `goal_reps` reaches `goal_weight_kg`.
- **`get_load_data(data_dir, exercise_id, weeks_ahead=4) -> dict`** -- returns historical and projected per-session training load. Never stored; recalculated on every call. Shape: `{"history": [{date, session_type, load}], "plan": [{date, session_type, load}]}`.
- **YAML as source of truth** -- `config.py` now calls `load_model_config()` at import time. All constants (`REST_REF_SECONDS`, `DAY_SPACING`, `SCHEDULE_*_DAYS`, etc.) load from `exercises.yaml` with Python literals as fallback. User overrides at `~/.bar-scheduler/exercises.yaml` are now active for all engine constants.
- **`docs/FAQ.md`** -- new document covering session types, weight prescription, bodyweight normalization, goals, TEST recovery, training load, and fitness-fatigue model.

### Fixed

- **`exercises.yaml` schedule section corrected** -- `SCHEDULE_2_DAYS` was `["S", "E"]`, now `["S", "H"]`. `SCHEDULE_5_DAYS` and `DAY_SPACING` were missing from YAML; both added.

---

## [0.4.3] -- 2026-03-24

### Breaking changes

- **`exercise_id` default removed** -- the following 7 API functions no longer default to `"pull_up"`. Callers must supply `exercise_id` explicitly:
  `get_plan`, `refresh_plan`, `get_training_status`, `get_onerepmax_data`, `get_volume_data`, `get_progress_data`, `get_overtraining_status`.
- **`get_band_progression()` renamed to `get_assist_progression(exercise_id)`** -- name reflects that the concept applies to any assistive equipment (bands, machine), not bands only. The function now takes a required `exercise_id` parameter and reads the progression from the exercise's YAML definition.
- **`get_next_band_step(item_id)` signature changed** -- now `get_next_band_step(item_id, exercise_id)`. The progression order is read from the exercise's YAML definition.
- **`get_bss_elevation_heights()` removed** -- BSS elevation height is assumed to be present (like a bar for pull-ups) and is not tuned by the planner. No replacement.

### Added

- **`equipment` block in per-exercise YAML files** -- `pull_up.yaml`, `dip.yaml`, and `bss.yaml` now each contain an `equipment:` section defining all valid equipment items (label, assistance_kg) for that exercise. Equipment data is no longer hardcoded in Python.
- **`assist_progression` in per-exercise YAML files** -- exercises that support assistive equipment (`pull_up`, `dip`) define an `assist_progression` list ordered from most-assistive to unassisted. Used for automatic step-down logic. Exercises without fixed-assistance options (`bss`) omit this field (defaults to `[]`).
- **`ExerciseDefinition.equipment`** -- new optional field (`dict[str, dict]`, default `{}`).
- **`ExerciseDefinition.assist_progression`** -- new optional field (`list[str]`, default `[]`).
- **`get_assist_progression(exercise_id) -> list[str]`** in public API -- returns the exercise's assist progression list.

### Removed

- `PULL_UP_EQUIPMENT`, `DIP_EQUIPMENT`, `BSS_EQUIPMENT`, `_CATALOGS` module-level constants from `core/equipment.py`. Use `get_catalog(exercise_id)` (now reads from the registry) or `get_exercise(exercise_id).equipment` directly.
- `BAND_PROGRESSION` module-level constant from `core/equipment.py`. Use `get_exercise(exercise_id).assist_progression`.
- `BSS_ELEVATION_HEIGHTS` module-level constant from `core/equipment.py`. Elevation height options are not tracked by the planner.

---

## [0.4.2] -- 2026-03-24

### Breaking changes

- **`init_profile` signature changed** -- removed `sex`, `days_per_week`, `exercises` parameters. New signature: `init_profile(data_dir, height_cm, bodyweight_kg, *, language="en", rest_preference="normal")`. Use `enable_exercise()` to add exercises after profile creation.
- **`enable_exercise` requires `days_per_week`** -- new required keyword argument. Old calls without it will raise `TypeError`.
- **`update_profile` signature changed** -- removed `sex`, `preferred_days_per_week`, `max_session_duration_minutes` parameters.
- **`update_equipment` signature changed** -- `active_item` parameter removed. Equipment item selection is now automatic.
- **`get_current_equipment` return shape changed** -- key renamed from `active_item` to `recommended_item`. Value is now auto-selected by the planner.
- **`UserProfile` fields removed** -- `sex`, `preferred_days_per_week`, `max_session_duration_minutes` no longer exist. Profiles serialised with these fields will silently ignore them on load.
- **`EquipmentState.active_item` removed** -- field no longer exists. Equipment snapshots (per-session historical records) retain `active_item` unchanged.
- **`days_for_exercise()` raises `KeyError`** -- the `preferred_days_per_week` global fallback has been removed. Every enabled exercise must have an explicit entry in `exercise_days`.

### Added

- **`recommend_equipment_item(available_items, exercise, current_tm, recent_history) -> str`** in `core/equipment.py` -- auto-selects the appropriate equipment item. Priority order: `WEIGHT_BELT` when `TM > weight_tm_threshold`; band step-down when `check_band_progression()` passes; heaviest available band; `BAR_ONLY` fallback.
- **Leff-1RM Epley weight prescription** -- added weight now uses the Epley inverse formula for all session types (S, H, E, T). Each session type targets a different rep count: S→5, H→8, E→12, T→6, corresponding to ~85/78/67/83% of 1RM. Conservative fallback (no history) uses TM to estimate 1RM.

### Changed

- **`snapshot_from_state(state, active_item)`** -- `active_item` is now an explicit parameter instead of being read from `state.active_item`.
- **`log_session` auto-selects equipment item** -- calls `recommend_equipment_item()` at log time to determine `active_item` for the snapshot.
- **`overtraining_severity` uses per-exercise days** -- previously read `profile.preferred_days_per_week`; now reads `profile.days_for_exercise(exercise_id)`.

### Removed

- `Sex = Literal["male", "female"]` type alias deleted.
- `UserProfile.sex`, `UserProfile.preferred_days_per_week`, `UserProfile.max_session_duration_minutes` fields deleted.
- `EquipmentState.active_item` field deleted.
- `weight_increment_fraction` linear formula replaced entirely by Epley inverse.

---

## [0.4.1] -- 2026-03-23

### Breaking changes

- **i18n removed** -- `core/i18n.py` and all locale YAML files (`en.yaml`, `ru.yaml`, `zh.yaml`) deleted. The library engine is English-only internally. `profile.language` remains a plain string, stored as a hint for clients. Clients (CLI, bots) own their own translation layer.
- **`list_languages` removed** -- function no longer exists. Clients manage their own language lists.
- **`update_language` now accepts any non-empty string** -- previously validated against `available_languages()`; validation is now the client's responsibility.

### Added

- **15 new API functions** eliminating the need for any direct `UserStore` or `core.equipment` imports by consumers:
  - Store operations: `set_plan_start_date`, `get_plan_weeks`, `set_plan_weeks`, `get_plan_cache_entry`, `delete_exercise_history`
  - Equipment queries: `get_current_equipment`, `check_band_progression`
  - Pure computations: `compute_leff`, `compute_equipment_adjustment`, `get_assistance_kg`, `get_next_band_step`, `get_band_progression`, `get_bss_elevation_heights`
  - Input parsers: `parse_sets_string`, `parse_compact_sets`
- **`exercises` optional in `init_profile`** -- defaults to `[]`; exercises added later via `enable_exercise`.
- **`get_exercise_info` / `list_exercises`** now return `session_params` (per session-type params dict) and `onerm_explanation` string.
- **`log_session` auto-attaches equipment snapshot** -- reads current equipment from profile when no snapshot is provided.
- **`get_data_dir()`** moved to `api.py` as a public utility (was private in `io/user_store.py`).

---

## [0.4.0] -- 2026-03-23

### Breaking changes

- **CLI extracted** -- the interactive command-line interface has been moved to a separate project ([cli_bar](https://github.com/bvpotapenko/cli_bar)). This package is now a pure Python library; no entry points are installed.
- **`HistoryStore` → `UserStore`** -- `io/history_store.py` class renamed and redesigned as a profile-centric store. Constructor changed from `(history_path, exercise_id)` to `(data_dir)`. All exercise-specific methods now take `exercise_id` as an explicit parameter. A `HistoryStore = UserStore` alias is provided for external consumers.
- **`update_bodyweight` signature** -- `exercise_id` parameter removed. Bodyweight is user-level, not per-exercise. New signature: `update_bodyweight(data_dir, bodyweight_kg)`.
- **`update_equipment` signature** -- dict parameter replaced with explicit named keyword arguments: `active_item`, `available_items`, `machine_assistance_kg`, `elevation_height_cm`, `valid_from`.
- **REST session type removed** -- `session_type="REST"` no longer exists. `SessionType` is now `Literal["S", "H", "E", "T", "TEST"]`. Calendar gaps serve as implicit rest.
- **Per-exercise plan cache** -- plan cache files renamed from `plan_cache.json` (shared) to `{exercise_id}_plan_cache.json` (per-exercise).

### Added

- **Public API module** (`src/bar_scheduler/api/api.py`) -- complete `data_dir`-isolated facade over the planning engine. All functions return JSON-serialisable dicts; no internal imports required by consumers. New public functions:
  - `init_profile`, `get_profile`, `update_profile` (now includes `height_cm`, `sex`)
  - `update_bodyweight`, `update_language`
  - `update_equipment`
  - `list_exercises`, `set_exercise_target`, `set_exercise_days`
  - `enable_exercise`, `disable_exercise`
  - `log_session`, `delete_session`, `get_history`
  - `get_plan`, `refresh_plan`, `explain_session`
  - `get_training_status`, `get_onerepmax_data`, `get_volume_data`, `get_progress_data`, `get_overtraining_status`
- **Typed exceptions**: `ProfileAlreadyExistsError`, `ProfileNotFoundError`, `HistoryNotFoundError`, `SessionNotFoundError`.
- **Multi-user support** -- every API function takes `data_dir: Path`; point different users at different directories.

### Documentation

- `docs/api_info.md` -- fully rewritten to document the public API; no internal imports in any example.
- `docs/features.md` -- updated to reflect library-only scope; CLI-specific features removed.
- `README.md` -- rewritten as a library README with links to docs and the CLI project.

---

## [0.3.0] -- 2026-03-04

### Added (i18n -- multilingual interface)

- `core/i18n.py` -- `t(key, **kwargs)`, `set_language()`, `available_languages()`; YAML locale files in `src/bar_scheduler/locales/`
- Three bundled locales: **en** (English), **ru** (Russian), **zh** (Chinese Mandarin)
- `--lang` / `-l` flag on the root command for per-session language override (does not persist)
- Language stored in `profile.json` under `"language"` key; omitted when English (backward compat with old profiles)
- Fallback chain: `--lang` → `profile.json` → `"en"`

### Added (`profile` subcommand group)

All profile-management commands are now grouped under `bar-scheduler profile`:

- `profile init` -- create / update user profile
- `profile update-weight <kg>` -- update bodyweight (positional argument, not a flag)
- `profile update-equipment` -- manage training equipment per exercise
- `profile update-language <lang>` -- save display language to `profile.json`

Interactive menu: `[l]` shortcut calls `_menu_update_language()` helper directly.
`HistoryStore.update_language()` writes / removes the `"language"` key in `profile.json`.

**Breaking change:** `bar-scheduler init`, `bar-scheduler update-weight`, and `bar-scheduler update-equipment` no longer exist as top-level commands. Use `bar-scheduler profile <subcommand>`.

---

### Fixed (plan prescription stability -- retroactive prescription change on session log)

**Bug:** Logging a session at date D retroactively changed the prescription for D and
earlier dates. Concrete example: `03.01 Tec: 2x5/120s` before logging → `03.01 Tec: 4x3+1kg/295s`
after logging. The session type for `03.03` also changed (End → Hpy).

**Root cause:** `_plan_core()` used ALL history (no date filter) for three pieces of initial state:

| Affected computation | Effect of logging session at D |
|---|---|
| `get_next_session_type_index(history, schedule)` | Rotation index shifts → ALL session types change |
| `_init_grip_counts(history, exercise)` | Grip counts shift → ALL grips change |
| `get_training_status(history, …)` + `ff_state` | TM + readiness change → sets/reps change |

Per-slot `recent_same_type = history_by_type.get(type, [])[-5:]` also had no date filter,
so logging at D changed adaptive rest for D itself.

**Invariant:** `prescription(slot D) = f(history where date < D, profile)`

**Fix:** Two targeted changes in `_plan_core()` (`core/planner.py`):

1. **`history_for_init`** -- filter to sessions with `date < start_date` for all initial state:
   - `get_training_status(effective_init, …)` → TM + ff_state
   - `get_next_session_type_index(effective_init, schedule)` → rotation
   - `_init_grip_counts(effective_init, exercise)` → grip counts
   - `len(effective_init)` → autoregulation gate and history_sessions count
   - `last_test_weight` from `effective_init` (BSS)
   - `effective_init = history_for_init if history_for_init else history` (brand-new user fallback)

2. **Per-slot date filter** -- `recent_same_type` now filtered to `date < slot_date`:
   ```python
   recent_same_type = [s for s in history_by_type[session_type] if s.date < date_str][-5:]
   ```
   Future slots (D2 > D1) still benefit from sessions logged at D1 -- only current/past slots
   are protected.

**Tests:** `TestPlanStability` removed (tested obsolete auto-advance formula). Replaced with
`TestPlanPrescriptionStability` (8 tests) covering: prescription stable after logging on plan_start,
session type stable, past slot prescription stable, rotation anchored to pre-plan history,
adaptive rest for current slot uses only pre-plan sessions, future slot adapts to logged session,
grip rotation stable.

| Change | Location |
|--------|----------|
| `history_for_init` + `effective_init` for all initial state | `core/planner.py` `_plan_core()` |
| `recent_same_type` filtered per-slot by `date < date_str` | `core/planner.py` `_plan_core()` loop |
| Remove `TestPlanStability`; add `TestPlanPrescriptionStability` (8 tests) | `tests/test_plan_integration.py` |
| §2 updated with stability invariant + `effective_init` pipeline | `docs/plan_logic.md` |

---

### -- 2026-03-03

### Fixed (backward-skip REST deletion when `plan_start < from_date`)

**Bug:** When `plan_start < from_date` (e.g., a "done" session exists before
the first missed session), backward skip deleted REST records that should be
preserved.  Concrete example: REST at 02.28, plan_start=03.01, skip from
03.02 by −1 → REST at 02.28 was deleted (wrong); plan shifted back but the
pre-existing REST was lost.

**Root cause:** The backward skip used a single variable (`target_dt = plan_start
+ shift_days`) for two distinct purposes:
1. Computing the new `plan_start` (correct: `plan_start + shift_days`)
2. Computing the REST removal lower bound (WRONG: should be `from_date + shift_days`)

When `plan_start = 03.01` and `from_date = 03.02` and `shift = −1`:
- `plan_start + shift = 02.28` → removal range `[02.28, 03.02)` → deletes REST at 02.28 (BUG)
- `from_date + shift = 03.01` → removal range `[03.01, 03.02)` → nothing removed (CORRECT)

**Fix:** Split into two separate computations (`planning.py` backward skip block):
- `new_plan_start_dt = plan_start_dt + timedelta(days=shift_days)` (plan anchor)
- `rest_lower_dt = from_dt + timedelta(days=shift_days)` (REST removal lower bound)

| Scenario | REST range (old, buggy) | REST range (new, correct) |
|---|---|---|
| plan_start=03.01, from_date=03.02, shift=−1 | [02.28, 03.02) -- deletes 02.28! | [03.01, 03.02) -- nothing |
| plan_start=03.06, from_date=03.06, shift=−6 | [02.28, 03.06) -- same | [02.28, 03.06) -- same |
| plan_start=03.01, from_date=03.05, shift=−3 | [02.26, 03.05) | [03.02, 03.05) -- undo fwd skip |

**Tests:** All skip tests replaced with comprehensive expected-behavior tests
(`TestSkipForwardExpected` + `TestSkipBackwardExpected`, 16 tests total).
Old classes removed: TestSkipPlanShift, TestSkipBackward,
TestSkipBackwardFromDateOffset, TestSkipForwardCalendarDays,
TestSkipForwardPlanStartOffset.

| Change | Location |
|--------|----------|
| `rest_lower_dt = from_dt + timedelta(days=shift_days)` | `cli/commands/planning.py` backward path |
| 5 old skip test classes removed; 2 new comprehensive classes added | `tests/test_plan_integration.py` |
| §7 updated with two-formula documentation | `docs/plan_logic.md` |

---

### -- 2026-03-02

### Fixed (backward-skip no-op when `from_date ≠ plan_start`)

**Bug:** When the user entered a `from_date` that was ahead of `plan_start`
(e.g., `from_date = plan_start + 1`) and shift = −1, the old formula
`target = from_date + shift_days` landed exactly at `plan_start` → no-op.
The plan appeared unchanged after the backward skip.

**Root cause:** Backward skip computed `target = from_date + shift_days`.
When `from_date > plan_start`, the target could equal (or be above) `plan_start`,
leaving the anchor unchanged.

**Fix:** `target = plan_start_date + shift_days` -- always shifts the anchor by
exactly `|shift_days|` calendar days, symmetric with forward skip. The `from_date`
is kept only as the upper bound for plan-REST removal.

| Change | Location |
|--------|----------|
| `target_dt = plan_start_dt + timedelta(days=shift_days)` | `cli/commands/planning.py` backward path |
| Existing `TestSkipBackward` tests updated to set `plan_start = from_date` | `tests/test_plan_integration.py` |

**Tests added:** `TestSkipBackwardFromDateOffset` (3 tests) -- covers:
from_date 1 day ahead of plan_start; from_date 2 days ahead; regression guard
for from_date = plan_start (both formulas agree).

---

### -- 2026-03-01

### Fixed (forward-skip calendar-day invariant when `plan_start < from_date`)

**Bug:** When the exercise had a "done" session at `plan_start` before the first
missed session at `from_date` (i.e., `plan_start < from_date`), a forward skip +N
scrambled session-type rotation and shifted sessions by more than N days.

**Root cause:** `skip()` only added REST records and relied on `plan()`'s
auto-advance (`plan_start = last_REST + 1`) to shift the anchor.
When `plan_start < from_date`, this formula jumps `plan_start` by
`(from_date − old_plan_start) + 1` days instead of exactly N days.

**Fix:**

| Change | Location | Detail |
|--------|----------|--------|
| `skip()` forward path now explicitly sets `plan_start = old_plan_start + N` | `cli/commands/planning.py` | Guarantees calendar-day invariant regardless of gap between plan_start and from_date |
| Auto-advance block removed from `plan()` | `cli/commands/planning.py` | `skip()` is now sole owner of plan_start advancement; the old auto-advance would override the correct value set by skip |

**Tests added:** `TestSkipForwardPlanStartOffset` (3 tests) in
`tests/test_plan_integration.py` -- covers: +1 from non-plan_start shifts all
sessions by exactly 1 day; session types preserved; regression guard for the
original pull_up scenario (plan_start == from_date still works).

---

### -- 2026-02-27

### Fixed (explain accuracy -- 6 bugs in `explain_plan_entry()`)

| # | Bug | Fix |
|---|-----|-----|
| A | REST sessions counted in grip rotation | Added `s.session_type != "REST"` filter to history in `explain_plan_entry()` |
| B | Week-number anchor used REST date as epoch | Same REST filter applied to `original_history` (week-anchor branch) |
| C | BSS `last_test_weight` always 0.0 | `last_test_weight` now extracted from last TEST completed_sets before `_calculate_added_weight()` |
| D | Inline autoregulation diverged from `apply_autoregulation()` | Replaced inline block with `apply_autoregulation()` call |
| E | `same_type_sessions` not capped to 5 | Added `[-5:]` slice to match `generate_plan()` |
| F | `has_variant_rotation` not checked; DIP showed cycle text | Guard added; non-rotating exercises always use `primary_variant` |

### Added (rest-adherence feedback in `calculate_adaptive_rest()`)

- Reads `rest_seconds_before` from all completed sets across the last 5 same-type sessions
  (values of 0 excluded -- first set of each session).
- Fires when `len(actual_rests) >= 3`:
  - avg actual rest < `rest_min × 0.85` → prescription −20 s
  - avg actual rest > `rest_max × 1.10` → prescription +20 s
- Signal is weaker than RIR/z-score signals (±20 s vs ±15–30 s); intended as a soft nudge
  toward the user's observed behaviour rather than a hard override.
- Adherence signal is now also shown in `explain` output under the REST section.

### Added (YAML exercise definitions)

- `exercises:` block added to `src/bar_scheduler/exercises.yaml` -- all three exercises
  (pull_up, dip, bss) fully defined in YAML with all `ExerciseDefinition` fields.
- `core/exercises/loader.py` -- `exercise_from_dict()` + `_validate_session_params()` with
  missing-field detection; `load_exercises_from_yaml()` returns `None` (not raises) on any failure.
- `core/exercises/registry.py` -- `_build_registry()` tries YAML first, falls back silently to
  Python constants (pull_up.py / dip.py / bss.py) if PyYAML is absent, YAML is malformed, or
  any required field is missing.
- `docs/exercise-structure.md` -- full field-by-field schema for `ExerciseDefinition` and
  `SessionTypeParams`, `grip_cycles` rules, validator behaviour, user-override guide, and
  complete worked example for adding a new "ring_row" exercise.
- 6 new tests in `TestYamlExerciseLoading` covering field validation, registry fallback,
  and key-field parity between YAML and Python constants.

### Refactored (`explain_plan_entry()` as thin wrapper over `generate_plan()`)

- **`_plan_core()` generator** extracted as the single source of truth for all plan logic.
  Yields `(SessionPlan, _SessionTrace)` per session.  Both `generate_plan()` and
  `explain_plan_entry()` delegate here -- the explanation is now mathematically guaranteed
  to match the plan.
- **`_SessionTrace` dataclass** captures every intermediate value (TM, grip counts, weekly_log,
  adj_sets/reps/rest, recent_same_type, etc.) at yield time.  No recomputation in the formatter.
- **`generate_plan()`** body replaced with a one-line list comprehension over `_plan_core()`.
- **`_format_explain()`** extracted as a pure formatting function; `explain_plan_entry()` is
  now 12 lines (down from 347).
- 11 new tests in `TestExplainWrapper` covering all session types, BSS weight, DIP no-cycle
  display, not-found warning, first-week / week-2 progression, autoreg-off display.

---

### -- 2026-02-26

### Refactored (codebase cleanup)

#### Dead code removal
- Deleted `format_plan_table`, `print_plan`, `print_plan_with_context`, and
  `format_plan_table_with_marker` from `cli/views.py` -- all four were superseded by
  `print_unified_plan` + `build_timeline` and had zero callers outside the file.

#### `build_timeline` -- index-based history matching
- Replaced `id()`-based object-identity tracking (`history_id_map`, `matched_history`)
  with direct original-index tracking (`matched_indices`).
  Same semantics; eliminates reliance on CPython memory-address stability.

#### `planning.py` -- DRY helpers
- Added `_resolve_plan_start(store, user_state, default_offset_days)` helper.
- Added `_total_weeks(plan_start_date, weeks_ahead)` helper.
- Removed 4 inline copies of the plan-start resolution + weeks-clamping blocks from
  `plan()`, `explain()`, `_menu_explain()`, and `skip()`.

#### `planner.py` -- O(1) recent-session lookup
- `generate_plan()` now builds a `history_by_type` dict before the session loop.
  Replaces a per-iteration O(n) history scan for `recent_same_type` with an O(1) dict lookup.

#### `metrics.py` -- single-pass linear regression
- `linear_trend_max_reps()` replaced four separate `sum()` generator passes with a
  single accumulator loop -- same result, one pass over the data.

#### `views.py` -- decomposed `print_unified_plan`
- Extracted four private helper functions from the 224-line `print_unified_plan`:
  `_print_equipment_header`, `_emax_cell`, `_grip_legend_str`, `_print_band_progression`.
- Moved `get_exercise` import from lazy local import to module-level.

---

### -- 2026-02-24

### Added (task.md completion batch)

#### Multi-exercise architecture
- **Exercise registry** (`core/exercises/`) with `ExerciseDefinition` dataclass.
  Pull-Up (`bw_fraction=1.0`), Parallel Bar Dip (`bw_fraction=0.92`), and BSS
  (`bw_fraction=0.71`) all share one planning engine, parameterised by
  `ExerciseDefinition`.
- **Per-exercise history files** -- `pull_up_history.jsonl`, `dip_history.jsonl`,
  `bss_history.jsonl`; backward-compatible with old `history.jsonl`.
- **`--exercise` / `-e` flag** on all CLI commands (default: `pull_up`).
- **BSS unilateral display** -- `_fmt_prescribed()` appends "(per leg)" for BSS.

#### 1RM display (`bar-scheduler 1rm`)
- Epley formula: `1RM = Leff × (1 + reps/30)`.
- Per-exercise `bw_fraction` applied to `Leff`; `onerm_includes_bodyweight`
  field controls display logic.
- `--json` output includes `1rm_kg`, `best_reps`, `best_date`, `effective_load_kg`.

#### Assessment test protocols
- `docs/assessment_protocols.md` -- pull-up, dip, BSS protocols.
- Per-exercise `test_frequency_weeks` field (`pull_up=3`, `dip=3`, `bss=4`).
- Planner auto-inserts TEST sessions at configured intervals via
  `_insert_test_sessions()`.

#### YAML config (#14)
- `src/bar_scheduler/exercises.yaml` -- all model constants documented in YAML
  with section headers and inline comments.
- `core/engine/config_loader.py` -- loads bundled YAML; merges user override
  from `~/.bar-scheduler/exercises.yaml` via deep-merge.
- `PyYAML>=6.0` added as an optional dependency (`pip install bar-scheduler[yaml]`
  or `pip install PyYAML`).

#### Profile fields (task.md §6)
- `UserProfile` gains four new fields with backward-compatible defaults:
  - `exercises_enabled: list` (default `["pull_up", "dip", "bss"]`)
  - `max_session_duration_minutes: int` (default `60`)
  - `rest_preference: str` (default `"normal"`, values: `"short"/"normal"/"long"`)
  - `injury_notes: str` (default `""`)
- `is_exercise_enabled(exercise_id)` method on `UserProfile`.
- Serializer updated; old `profile.json` files without the new keys load with defaults.
- `init` command preserves all four fields when re-initialising.

#### `help-adaptation` command (task.md §7)
- `bar-scheduler help-adaptation` prints the adaptation timeline table.
- `[a]` shortcut added to the interactive menu.
- Covers all stages: Day 1, Weeks 1–2, Weeks 3–4, Weeks 6–8, Weeks 12+.

#### Equipment-aware system
- `core/equipment.py` -- `PULL_UP_EQUIPMENT`, `DIP_EQUIPMENT`, `BSS_EQUIPMENT`
  catalogs; `BAND_PROGRESSION`; `compute_leff()`, `check_band_progression()`,
  `compute_equipment_adjustment()`.
- `EquipmentSnapshot` / `EquipmentState` dataclasses in `models.py`.
- `update-equipment` CLI command; `[u]` menu option.
- Equipment stored in `profile.json` under `"equipment"` key with
  `valid_from` / `valid_until` for history.

#### Track B max estimator
- `core/max_estimator.py` -- FI method (Pekünlü & Atalağ 2013) and Nuzzo method
  (Nuzzo et al. 2024) for estimating max reps from multi-set sessions.
- `eMax` column in unified plan shows actual (TEST), fi/nz estimate (past), or
  TM projection (future).

### Fixed (pullup_fixes_0.md batch)

| # | Issue | Fix |
|---|-------|-----|
| 11 | Plan instability | Frozen past prescriptions; schedule rotation resumes from last non-TEST; cumulative week counter |
| 2 | Weekly progression applied per session | Now applied once per calendar-week boundary |
| 6 | Rest double-counts in training load | `rest_stress_multiplier` removed from `w(t)` |
| 12 | Added weight ignores bodyweight | Formula: `BW × 0.01 × (TM−9)`, rounded 0.5 kg, capped per exercise |
| 13 | Static rest prescription | Adaptive rest: ±30 s based on RIR, drop-off, and readiness z-score |
| 1 | TM bypasses TM_FACTOR | Plan starts from `floor(0.9 × test_max)`, not raw test_max |
| 9 | Session params deviate from spec | S: 0.35/0.55 fractions; H rest: 120–180 s |
| 5 | Autoregulation gate too low | Raised from 5 → 10 sessions |
| 3 | Day spacing irregular | Fixed offsets: 3-day [0,2,4]; 4-day [0,1,3,5] |
| 10 | readiness_var init too low | Changed from 1.0 → 10.0 |
| 8 | TM capped at target | Removed cap; TM grows past user goal |
| 17 | Endurance volume multiplier | `kE(TM) = 3.0 + 2.0 × clip((TM−5)/25, 0, 1)` |
| 18 | SessionPlan validation unreachable | Moved before `@property total_reps` |

### Documentation

- `docs/adaptation_guide.md` -- complete adaptation timeline guide.
- `docs/training_model.md` -- added: ExerciseDefinition schema, bw_fraction table,
  1RM section (Epley, BW-inclusion rules), Plan Regeneration section (immutable
  history), YAML config reference table replacing old Python-only table.
- `docs/assessment_protocols.md` -- pull-up, dip, BSS test protocols.
- `docs/exercises/pull_up.md`, `dip.md`, `bss.md` -- per-exercise biomechanics
  and variant details.
- `README.md` -- added: Profile Configuration section, Config Customisation
  section, Adaptation Timeline summary, FAQ: Plan Changes, `help-adaptation`
  in command table, updated Project Structure.

---

## Earlier history (pre-changelog)

See git log for the full history of fixes made during the initial build
(`main` branch, commits through 2026-02-24).
