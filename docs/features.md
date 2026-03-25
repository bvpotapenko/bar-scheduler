# bar-scheduler -- Feature List

All features are accessible through the public Python API (`bar_scheduler.api.api`). See [api_info.md](api_info.md) for function signatures and return shapes.

---

## 1. Profile & User Management

| # | Feature | API function |
|---|---------|-------------|
| 1.1 | Create bare user profile (height, bodyweight, language, rest preference); exercises added separately via `enable_exercise` | `init_profile` |
| 1.2 | Read profile as dict (all fields + current bodyweight) | `get_profile` |
| 1.3 | Update any subset of profile fields surgically (preserves plan anchors, equipment, other internal keys) | `update_profile` |
| 1.4 | Update current bodyweight | `update_bodyweight` |
| 1.5 | Set display language | `update_language` |
| 1.6 | Profile fields: `height_cm`, `exercise_days`, `exercise_targets`, `exercises_enabled`, `language` | stored in `profile.json` |
| 1.7 | Multi-user isolation -- every function takes `data_dir: Path` | all functions |

## 2. Exercise Management

| # | Feature | API function |
|---|---------|-------------|
| 2.1 | List all registered exercises with full metadata (id, display_name, muscle_group, variants, rotation flag, bw_fraction, onerm_includes_bodyweight, session_params, onerm_explanation) | `list_exercises` |
| 2.2 | Enable an exercise for a user with required `days_per_week` (creates history file) -- idempotent | `enable_exercise` |
| 2.3 | Disable an exercise (history file preserved) | `disable_exercise` |
| 2.4 | Delete exercise history JSONL file permanently | `delete_exercise_history` |
| 2.5 | Set per-exercise rep goal (bodyweight or weighted) | `set_exercise_target` |
| 2.6 | Set per-exercise training frequency (1–5 days/week) | `set_exercise_days` |
| 2.7 | Four built-in exercises: Pull-Up (`bw_fraction=1.0`), Parallel Bar Dip (`bw_fraction=0.92`), BSS (`bw_fraction=0.71`), Incline Dumbbell Press (`bw_fraction=0.0`, per-hand weight) | -- |
| 2.8 | Single exercise metadata lookup by ID | `get_exercise_info` |

## 3. Equipment Management

| # | Feature | API function / notes |
|---|---------|---------------------|
| 3.1 | Configure equipment per exercise (bands, machine assistance, BSS elevation surface, discrete weight set) | `update_equipment` |
| 3.2 | Equipment history with valid-from / valid-until timestamps (append-only) | automatic |
| 3.3 | Equipment catalog per exercise | `get_equipment_catalog` |
| 3.4 | Effective load (Leff) computed from bodyweight fraction + added weight − assistance | `compute_leff` |
| 3.5 | Equipment snapshot attached to each logged session at log time | automatic |
| 3.6 | Current equipment state as a dict (exercise_id, recommended_item, available_items, assistance_kg, is_bss_degraded); recommended_item auto-selected from available_items by planner | `get_current_equipment` |
| 3.7 | Band progression readiness check (n consecutive sessions on current band) | `check_band_progression` |
| 3.8 | Equipment adjustment factor when switching bands (reps_factor, description) | `compute_equipment_adjustment` |
| 3.9 | Assistance kg for any item (including machine-assisted) | `get_assistance_kg` |
| 3.10 | Next item in assist progression for an exercise | `get_next_band_step(item_id, exercise_id)` |
| 3.11 | Full assist progression list for an exercise (YAML-driven, per-exercise) | `get_assist_progression(exercise_id)` |
| 3.12 | Per-exercise discrete weight set stored in profile (`available_weights_kg`); planner floor-snaps prescriptions to largest available weight ≤ ideal — no fractional or unavailable weights prescribed | `update_equipment(…, available_weights_kg=[…])` |

## 4. Training Log (Session Logging)

| # | Feature | API function |
|---|---------|-------------|
| 4.1 | Log a completed session (returns persisted session dict) | `log_session` |
| 4.2 | Same (date, session_type) replaces existing entry -- idempotent re-log | automatic |
| 4.3 | Read full session history (sorted by date) | `get_history` |
| 4.4 | Delete a session by 1-based history index | `delete_session` |
| 4.5 | Session fields: date, bodyweight_kg, grip, session_type, exercise_id, completed_sets, planned_sets, equipment_snapshot, notes | `SessionResult` model |
| 4.6 | Set fields: actual_reps, target_reps, added_weight_kg, rest_seconds_before, rir_target, rir_reported | `SetResult` model |
| 4.7 | `parse_sets_string` -- parse per-set strings and compact `N×reps/rest` notation | `parse_sets_string` |
| 4.8 | `parse_compact_sets` -- returns `None` for non-compact input (safe auto-detect) | `parse_compact_sets` |

## 5. Training Plan

| # | Feature | Notes |
|---|---------|-------|
| 5.1 | Unified timeline -- past (actual) and future (planned) sessions in one chronological list | `get_plan` → `sessions` |
| 5.2 | Prescription stability invariant: `prescription(D) = f(history date < D, profile)` | `_plan_core` in planner |
| 5.3 | Multi-week plan with configurable horizon | `get_plan(weeks_ahead=N)` |
| 5.4 | Session rotation: S (1-day); S→H (2-day); S→H→E (3-day); S→H→T→E (4-day); S→H→T→E→S (5-day) | automatic |
| 5.5 | Training max (TM) = floor(0.9 × latest TEST max) | automatic |
| 5.6 | Weekly TM progression -- nonlinear curve, slows near target | automatic |
| 5.7 | Autoregulation: sets/reps adjusted by readiness z-score (active after ≥10 sessions) | automatic |
| 5.8 | Adaptive rest: midpoint adjusted ±30/15 s based on RIR, set drop-off, readiness, and rest-adherence signal | automatic |
| 5.9 | Added weight for all weighted session types (S, H, E, T) -- Leff-1RM Epley inverse, 0.5 kg increments; weight starts when TM > exercise threshold | automatic |
| 5.10 | Endurance volume scales with TM via kE multiplier | automatic |
| 5.11 | TEST session auto-insertion at configured intervals per exercise | automatic |
| 5.12 | Grip rotation across sessions (pronated → neutral → supinated for pull-ups; fixed for dip) | automatic |
| 5.13 | Deload detection: plateau + low readiness, underperformance, or low compliance | automatic |
| 5.14 | Plan change diff vs. last cached plan | `get_plan` → `plan_changes` |
| 5.15 | Plan start date anchored per-exercise in profile; `refresh_plan` resets anchor to today | `refresh_plan` |
| 5.16 | Cumulative week numbering anchored to first session in history | automatic |
| 5.17 | Overtraining detection -- graduated warning (levels 0–3); volume/rest/rep reduction; plan start shifted forward at level ≥2 | `get_plan` → `overtraining`; `get_overtraining_status` |
| 5.18 | RIR feedback: RIR ≥4 sessions accumulate less fatigue (sub-neutral multiplier) | automatic |
| 5.19 | Track B max estimators: FI method (Pekünlü 2013) + Nuzzo 2024 shown per past session | `get_plan` → `sessions[].track_b` |
| 5.20 | Persist and recall plan horizon in weeks | `set_plan_weeks`, `get_plan_weeks` |
| 5.21 | Manually override plan start date per exercise | `set_plan_start_date` |
| 5.22 | Look up cached plan prescription for a specific (date, session_type) | `get_plan_cache_entry` |

## 6. Plan Explanation

| # | Feature | API function |
|---|---------|-------------|
| 6.1 | Plain-text explanation of any date: planned session, rest day, or historical session | `explain_session` |
| 6.2 | Explanation covers: TM formula, grip rotation, set config, adaptive rest breakdown, added weight formula | `explain_session` |
| 6.3 | Pass `"next"` to explain the first upcoming session | `explain_session(…, "next")` |
| 6.4 | Returns Rich markup string; strip to plain text with `Text.from_markup(text).plain` | -- |
| 6.5 | Overtraining shift notice when plan start was pushed forward | automatic |

## 7. Analysis

| # | Feature | API function |
|---|---------|-------------|
| 7.1 | Training status: TM, latest TEST, trend slope, plateau flag, deload flag, fitness-fatigue state | `get_training_status` |
| 7.2 | 1-rep max estimate -- Epley, Brzycki, Lander, Lombardi, Blended formulas + recommended formula | `get_onerepmax_data` |
| 7.3 | Weekly rep volume | `get_volume_data` |
| 7.4 | Progress data for plotting: TEST session history + trajectory projections (BW reps, goal-weight reps, 1RM added kg) | `get_progress_data` |
| 7.5 | Overtraining severity assessment (level 0–3) | `get_overtraining_status` |
| 7.6 | Fitness-fatigue model: G(t) fitness, H(t) fatigue, readiness, readiness z-score | `get_training_status` → `status["fitness"]` / `"fatigue"` / `"readiness_z_score"` |

## 8. Language

| # | Feature | Notes |
|---|---------|-------|
| 8.1 | Language code stored per user in `profile.json`; accepted by `init_profile` and `update_language` | `profile.language` |
| 8.2 | `update_language(data_dir, lang)` persists any language code; passing `"en"` removes the key (restores default) | `update_language` |
| 8.3 | Library engine is English-only internally; `profile.language` is a hint for clients (CLI, bots) to apply their own translation layer | -- |

## 9. Configuration & Customisation

| # | Feature | Notes |
|---|---------|-------|
| 9.1 | All model constants in `exercises.yaml` (bundled with package) | -- |
| 9.2 | User override at `~/.bar-scheduler/exercises.yaml` (deep-merge with defaults) | file override |
| 9.3 | YAML loader with graceful fallback to Python constants if PyYAML is absent | automatic |
| 9.4 | Add a custom exercise by creating a new YAML entry | see `docs/exercise-structure.md` |

---

*Last updated: 2026-03-25 (0.5.1: added incline_db_press exercise; added available_weights_kg to EquipmentState for discrete weight snapping).*
