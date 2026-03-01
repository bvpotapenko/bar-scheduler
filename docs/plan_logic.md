# plan_logic.md — bar-scheduler Technical Reference

---

## 1. Data Model

```
UserProfile          UserState               SessionResult
  days_per_week   ──▶  profile: UserProfile    date, session_type
  exercise_days        history: [SessionResult] bodyweight_kg, grip
  exercise_targets     current_bodyweight_kg   planned_sets, completed_sets
                                               exercise_id, equipment_snapshot

SessionPlan                  TimelineEntry
  date, session_type           planned: SessionPlan | None
  sets: [PlannedSet]           actual:  SessionResult | None
  expected_tm, week_number     status: done|rested|missed|next|planned|extra
  grip, exercise_id            actual_id (1-based, for delete-record)
                               track_b: {fi, nuzzo} | None

FitnessFatigueState
  fitness G(t), fatigue H(t)
  m_hat (estimated max), sigma_m
  readiness_mean, readiness_var
  .readiness()       → G - H
  .readiness_z_score() → (readiness - mean) / sqrt(var)
```

---

## 2. Plan Generation Pipeline

```
plan()  ←─ cli/commands/planning.py
  │
  ├─ _resolve_plan_start(store, user_state)
  │    plan_start = stored OR (first_history + 1 day) OR (today + 1 day)
  │
  ├─ auto-advance (forward skip only):
  │    last_rest = max REST date in history
  │    if last_rest >= plan_start:
  │        plan_start = last_rest + 1 day          ← key: +1, not last_rest itself
  │        store.set_plan_start_date(plan_start)
  │
  ├─ overtraining_severity(history, days_per_week)
  │    → {level: 0-3, extra_rest_days: int, …}
  │
  ├─ generate_plan(user_state, plan_start, weeks_ahead, exercise, ot_level, ot_rest_days)
  │    → list[SessionPlan]
  │
  └─ build_timeline(plans, history) → list[TimelineEntry]
```

### generate_plan / _plan_core  ← core/planner.py

```
_plan_core(user_state, start_date, …)   [generator]
  │
  ├─ filter history: exercise_id + session_type != "REST"
  ├─ status = get_training_status(history, bodyweight_kg, baseline_max)
  │    training_max = floor(0.9 × latest_test_max)        [core/metrics.py]
  │    ff_state = build_fitness_fatigue_state(history, …)
  │
  ├─ if ot_rest_days > 0: start_date += ot_rest_days
  │
  ├─ schedule = get_schedule_template(days_per_week)       → e.g. ["S","H","E"]
  ├─ rotation_idx = get_next_session_type_index(history, schedule)
  │    filters: session_type not in ("TEST","REST")
  │
  ├─ grip_counts = _init_grip_counts(history, exercise)    → {} if no rotation
  │
  └─ for each (date, session_type) in calculate_session_days(start_date, …):
        tm_float += expected_reps_per_week(TM, target)    [once per calendar week]
        week_number = (date - first_monday).days // 7 + 1
        grip = _next_grip(session_type, grip_counts, exercise)
        sets = calculate_set_prescription(session_type, TM, ff_state, …)
        yield SessionPlan(date, session_type, sets, expected_tm, week_number, grip)
```

---

## 3. Session Date Arithmetic

```
calculate_session_days(start_date, days_per_week, num_weeks)

DAY_OFFSETS per days_per_week:
  1 → [0]
  2 → [0, 3]
  3 → [0, 2, 4]
  4 → [0, 1, 3, 5]
  5 → [0, 1, 2, 4, 5]

For week w (0-indexed), slot i:
  date = start_date + w*7 + DAY_OFFSETS[i]

All sessions shift uniformly by ΔN when start_date shifts by ΔN.
```

---

## 4. Session Type Rotation

```
SCHEDULE templates (from exercises.yaml / config.py):
  1-day  : [S]
  2-day  : [S, H]
  3-day  : [S, H, E]
  4-day  : [S, H, T, E]
  5-day  : [S, H, T, E, S]

TEST sessions inserted every N weeks per exercise protocol.
TEST does NOT advance the S/H/T/E rotation index.

get_next_session_type_index(history, schedule):
  count = number of non-TEST, non-REST sessions in history
  return count % len(schedule)
```

---

## 5. Grip Rotation

```
_init_grip_counts(history, exercise) → dict[session_type → count]
  Returns {} immediately if exercise.has_variant_rotation == False

_next_grip(session_type, counts, exercise) → str
  cycle = exercise.grip_cycles[session_type]   # e.g. [pronated, neutral, supinated]
  grip = cycle[counts[session_type] % len(cycle)]
  counts[session_type] += 1
  return grip

pull_up grip cycles:
  S, H → pronated → neutral → supinated
  T    → pronated → neutral
  E, TEST → pronated (fixed)

dip: has_variant_rotation = False → always "standard", no Grip column shown.
```

---

## 6. Adaptation Modules

### Training Max (TM) Progression

```
initial TM = floor(0.9 × latest_test_max)          [core/metrics.py: training_max()]

Weekly increment (once per calendar-week boundary):
  prog = expected_reps_per_week(TM, user_target)   [core/adaptation.py]
  tm_float += prog                                  [within _plan_core]
  TM = round(tm_float)

expected_reps_per_week: nonlinear — faster when far below target, slower near it.
TM is NOT capped at target — it grows past user's goal.
```

### Autoregulation  ← apply_autoregulation()  [core/adaptation.py]

```
Gated at MIN_SESSIONS_FOR_AUTOREG = 10

z = ff_state.readiness_z_score()   # (readiness - mean) / sqrt(var)

if z < READINESS_Z_LOW  (-1.0):  sets = max(3, sets × 0.75)
if z > READINESS_Z_HIGH (+1.0):  reps += 1
else:                             no change

Reps reduction (overtraining level 3):  reps -= 1
Set drop (overtraining level 2+):       sets -= 1
```

### Overtraining Detection  ← overtraining_severity()  [core/adaptation.py]

```
Analyze last 7 calendar days:
  n          = non-REST sessions
  span_days  = last_date − first_date (days)
  rest_credit = REST records within span (from full_history)

  expected_interval = 7 / days_per_week  (days/session)
  expected_time     = n × expected_interval
  actual_time       = span_days + rest_credit
  extra_rest_days   = max(0, round(expected_time − actual_time))

level:  0 = none
        1 = 1 extra day  (mild)
        2 = 2-3 extra days  (moderate)
        3 = ≥4 extra days  (severe)

Applied in _plan_core:
  start_date  += ot_rest_days  (transient shift, not persisted)
  level 1: +30 s rest per session
  level 2: +60 s rest, -1 set
  level 3: +60 s rest, -1 set, -1 rep
```

### Fitness-Fatigue Model  ← build_fitness_fatigue_state()  [core/physiology.py]

```
G(t) = G(t−1) × e^(−Δt/TAU_FITNESS)  + k_G × w(t)   TAU_FITNESS = 42 days
H(t) = H(t−1) × e^(−Δt/TAU_FATIGUE) + k_H × w(t)   TAU_FATIGUE = 14 days

w(t) = session training load (sum of hard_reps × load_stress × variant_stress)

readiness(t) = G(t) − H(t)
readiness_mean ← EWMA(α=0.1)
readiness_var  ← EWMA(β=0.1)
z_score = (readiness − mean) / sqrt(var)
```

### Adaptive Rest  ← calculate_adaptive_rest()  [core/planner.py]

```
base = (params.rest_min + params.rest_max) / 2

Adjustments from last same-type session:
  any set RIR ≤ 1         → +30 s   (near failure)
  drop-off > threshold    → +15 s   (intra-session fatigue)
  all sets RIR ≥ 3        → −15 s   (easy session)

Readiness adjustment:
  z < READINESS_Z_LOW     → +30 s

Clamped: max(rest_min, min(rest_max, base))
```

---

## 7. Shift Mechanism (skip command)

```
skip()  ←─ cli/commands/planning.py

Inputs:  from_date (str), shift_days (int, ±N)

─── Forward skip (shift_days > 0) ────────────────────────────────────────
  1. Write N REST records at from_date, from_date+1, …, from_date+N−1
     (session_type="REST", exercise_id=exercise_id)
  2. Return. No plan_start_date change here.

  Next call to plan():
  3. Auto-advance detects last REST ≥ plan_start:
       plan_start = last_REST + 1 day
       store.set_plan_start_date(plan_start)
  4. Plan regenerates from new plan_start.
     REST records appear as status="rested" ("~") in timeline.

─── Backward skip (shift_days < 0) ────────────────────────────────────────
  1. target_date = from_date + shift_days   (shift_days < 0)
  2. Remove plan-REST records in gap [target_date, from_date)
  3. Clamp: if target_date < first_training_date:
               target_date = first_training_date
  4. store.set_plan_start_date(target_date)
  5. Plan regenerates from target_date.

Invariant: skip NEVER modifies user-submitted training logs.
           Only session_type="REST" records added by skip are added/removed.
           Use delete-record to manage training logs.
```

---

## 8. Timeline Construction  ← build_timeline()  [cli/views.py]

```
build_timeline(plans: list[SessionPlan], history: list[SessionResult]) → list[TimelineEntry]

Week anchor:
  first_date   = min(s.date for s in history if s.session_type != "REST")
  first_monday = first_date − timedelta(days=first_date.weekday())
  week_number  = (date − first_monday).days // 7 + 1

Matching (by date, earliest unmatched plan first):
  For each plan slot:
    Look for unmatched history session on same date
    Preference: same session_type; fallback: any type

Status assignment:
  actual present, type != REST  → "done"   icon ✓
  actual present, type == REST  → "rested" icon ~
  no actual, date in past        → "missed" icon —
  no actual, date in future      → "planned" (first = "next") icon > or space
  unmatched history entry        → "extra"  icon ·

eMax column (_emax_cell()):
  past TEST session   → actual max reps
  past non-TEST ≥2 sets → "fi/nz"  (FI method / Nuzzo estimate)
  future planned      → max(round(expected_tm / 0.9), floor_max)
  (suppressed if equal to previous row's value)
```

---

## 9. Auto-Advance Rule

```
Condition: last REST date >= current plan_start_date
Action:    plan_start_date = last_REST_date + 1 day

Why +1 (not last_REST):
  If plan_start == REST_date, the REST record matches plan slot 0,
  consuming that session-type slot and breaking rotation.
  With plan_start = REST + 1, the REST falls before plan_start →
  appears as unmatched history ("~"), slot 0 is the correct next type.

Backward skip sets plan_start_date directly to target_date (no REST at target).
The auto-advance does not trigger (no REST at or after target_date by construction).
```

---

## 10. Key Constants

| Constant | Value | Location |
|---|---|---|
| `TM_FACTOR` | 0.90 | config.py |
| `TAU_FITNESS` | 42 days | config.py |
| `TAU_FATIGUE` | 14 days | config.py |
| `MIN_SESSIONS_FOR_AUTOREG` | 10 | config.py |
| `READINESS_Z_LOW` | -1.0 | config.py |
| `READINESS_Z_HIGH` | +1.0 | config.py |
| `PLATEAU_SLOPE_THRESHOLD` | 0.5 reps/week | config.py |
| `PLATEAU_WINDOW_DAYS` | 42 | config.py |
| `DELOAD_VOLUME_REDUCTION` | 0.50 (50%) | config.py |
| `REST_REF_SECONDS` | 180 s | config.py |
| `endurance_volume_multiplier(TM)` | 3.0 + 2.0 × clip((TM−5)/25, 0, 1) | adaptation.py |
| `DROP_OFF_THRESHOLD` | ~0.15 (15%) | planner.py |
| `A_RIR` | 0.1 | config.py |

---

## 11. File Map

```
src/bar_scheduler/
  core/
    models.py          ← dataclasses (SessionResult, SessionPlan, FitnessFatigueState, …)
    planner.py         ← _plan_core, generate_plan, calculate_session_days, build_timeline,
                          _init_grip_counts, _next_grip, calculate_set_prescription,
                          calculate_adaptive_rest, explain_plan_entry
    adaptation.py      ← get_training_status, overtraining_severity, apply_autoregulation,
                          should_deload, detect_plateau, check_underperformance
    physiology.py      ← update_fitness_fatigue, build_fitness_fatigue_state,
                          rir_effort_multiplier, load_stress_multiplier,
                          calculate_session_training_load
    metrics.py         ← training_max, readiness_z_score, effective_reps,
                          bodyweight_normalized_reps, estimate_1rm, linear_trend_max_reps
    max_estimator.py   ← estimate_max_reps_from_session (FI + Nuzzo Track B)
    config.py          ← all numeric constants
    exercises/
      base.py          ← ExerciseDefinition dataclass
      registry.py      ← get_exercise(id)
      loader.py        ← YAML merge loader
  cli/
    app.py             ← typer app, get_store(), ExerciseOption
    main.py            ← main_callback, interactive menu
    commands/
      planning.py      ← plan, explain, skip, _resolve_plan_start, _total_weeks
      sessions.py      ← log_session, show_history, delete_record
      profile.py       ← init, update_weight, update_equipment
      analysis.py      ← status, volume, plot_max, onerepmax
    views.py           ← print_unified_plan, build_timeline, _fmt_prescribed, _fmt_actual
  io/
    history_store.py   ← HistoryStore (load/save history + profile + equipment)
    serializers.py     ← JSONL read/write, backward compat
exercises/
  pull_up.yaml         ← pull-up params + grip cycles
  dip.yaml             ← dip params (no grip rotation)
  bss.yaml             ← Bulgarian split squat params
```
