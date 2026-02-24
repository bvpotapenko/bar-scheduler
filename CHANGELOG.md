# Changelog

All notable changes to bar-scheduler are documented here.

---

## [Unreleased] — 2026-02-24

### Added (task.md completion batch)

#### Multi-exercise architecture
- **Exercise registry** (`core/exercises/`) with `ExerciseDefinition` dataclass.
  Pull-Up (`bw_fraction=1.0`), Parallel Bar Dip (`bw_fraction=0.92`), and BSS
  (`bw_fraction=0.71`) all share one planning engine, parameterised by
  `ExerciseDefinition`.
- **Per-exercise history files** — `pull_up_history.jsonl`, `dip_history.jsonl`,
  `bss_history.jsonl`; backward-compatible with old `history.jsonl`.
- **`--exercise` / `-e` flag** on all CLI commands (default: `pull_up`).
- **BSS unilateral display** — `_fmt_prescribed()` appends "(per leg)" for BSS.

#### 1RM display (`bar-scheduler 1rm`)
- Epley formula: `1RM = Leff × (1 + reps/30)`.
- Per-exercise `bw_fraction` applied to `Leff`; `onerm_includes_bodyweight`
  field controls display logic.
- `--json` output includes `1rm_kg`, `best_reps`, `best_date`, `effective_load_kg`.

#### Assessment test protocols
- `docs/assessment_protocols.md` — pull-up, dip, BSS protocols.
- Per-exercise `test_frequency_weeks` field (`pull_up=3`, `dip=3`, `bss=4`).
- Planner auto-inserts TEST sessions at configured intervals via
  `_insert_test_sessions()`.

#### YAML config (#14)
- `src/bar_scheduler/exercises.yaml` — all model constants documented in YAML
  with section headers and inline comments.
- `core/engine/config_loader.py` — loads bundled YAML; merges user override
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
- `core/equipment.py` — `PULL_UP_EQUIPMENT`, `DIP_EQUIPMENT`, `BSS_EQUIPMENT`
  catalogs; `BAND_PROGRESSION`; `compute_leff()`, `check_band_progression()`,
  `compute_equipment_adjustment()`.
- `EquipmentSnapshot` / `EquipmentState` dataclasses in `models.py`.
- `update-equipment` CLI command; `[u]` menu option.
- Equipment stored in `profile.json` under `"equipment"` key with
  `valid_from` / `valid_until` for history.

#### Track B max estimator
- `core/max_estimator.py` — FI method (Pekünlü & Atalağ 2013) and Nuzzo method
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

- `docs/adaptation_guide.md` — complete adaptation timeline guide.
- `docs/training_model.md` — added: ExerciseDefinition schema, bw_fraction table,
  1RM section (Epley, BW-inclusion rules), Plan Regeneration section (immutable
  history), YAML config reference table replacing old Python-only table.
- `docs/assessment_protocols.md` — pull-up, dip, BSS test protocols.
- `docs/exercises/pull_up.md`, `dip.md`, `bss.md` — per-exercise biomechanics
  and variant details.
- `README.md` — added: Profile Configuration section, Config Customisation
  section, Adaptation Timeline summary, FAQ: Plan Changes, `help-adaptation`
  in command table, updated Project Structure.

---

## Earlier history (pre-changelog)

See git log for the full history of fixes made during the initial build
(`main` branch, commits through 2026-02-24).
