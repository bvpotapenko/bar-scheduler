# Pull-Up Planner: Logic Error Analysis & Fix Tasks

**Date**: 2026-02-23  
**Analyzed files**: `planner.py`, `config.py`, `metrics.py`, `adaptation.py`, `physiology.py`, `models.py`, `training_model.md`

---

## Summary

10 logic errors and inconsistencies found. Priority breakdown:
- **CRITICAL**: 2
- **HIGH**: 1
- **MEDIUM**: 4
- **LOW**: 3

---

## Issue #1: Training max initialization bypasses TM_FACTOR formula

**Severity**: HIGH  
**Category**: LOGIC_ERROR  
**File**: `planner.py`  
**Location**: generate_plan(), line ~280-285

### Problem

The plan generator sets `tm = status.latest_test_max or status.training_max`, which means if a TEST session exists, TM is set to the raw test max (e.g., 10 reps) instead of floor(0.9 × 10) = 9 as documented.

This causes the plan to immediately prescribe at the user's proven ceiling, leaving no headroom for progression and likely resulting in failure on first planned sessions.

### Expected Behavior

TM should always be calculated as floor(0.9 × latest_test_max) per training_model.md

### Actual Behavior

Code uses latest_test_max directly: `tm = status.latest_test_max or status.training_max`

### Fix

Remove the override logic. Use `tm = status.training_max` consistently. The `get_training_status()` already computes TM correctly via `training_max(history)`.

### Test Case (for verification)

Given history with TEST session showing 10 reps:
- Expected TM = 9
- Current buggy TM = 10
Assert that generated plan prescriptions are based on TM=9, not TM=10.

---

## Issue #2: Weekly progression rate applied on every session instead of weekly

**Severity**: CRITICAL  
**Category**: LOGIC_ERROR  
**File**: `planner.py`  
**Location**: generate_plan() main loop, line ~320-330

### Problem

The code updates TM every time `sessions_in_week > sessions_per_week` (i.e., on each session), by calling `expected_reps_per_week(tm)` and adding the full weekly delta.

For a 3-day/week schedule with progression = 0.5 reps/week, the user gets:
- Session 1: TM += 0.5
- Session 2: TM += 0.5
- Session 3: TM += 0.5
= 1.5 reps/week instead of 0.5 reps/week.

### Expected Behavior

TM should increase by `expected_reps_per_week()` once per calendar week, not per session.

### Actual Behavior

TM increases on every session transition, multiplying weekly progression by number of sessions/week.

### Fix

Track `current_week` index separately. Only apply progression when transitioning to a new week:
```python
if sessions_in_week == 1 and current_week > 0:  # New week started
    progression = expected_reps_per_week(int(tm_float))
    tm_float = min(tm_float + progression, float(target))
```

### Test Case (for verification)

Generate 4-week plan with baseline_max=10 (TM=9), 3 days/week.
Expected: TM after 1 week ≈ 9.5
Current bug: TM after 1 week ≈ 10.5

---

## Issue #3: Day spacing calculation produces irregular rest days

**Severity**: MEDIUM  
**Category**: LOGIC_ERROR  
**File**: `planner.py`  
**Location**: calculate_session_days(), line ~85-115

### Problem

The function hardcodes rest_days logic inside the loop based on session type and position, but uses `rest_days + 1` for the date increment, which double-counts.

For 3-day schedule with `rest_days = max(min_rest, 2)`, the code does:
`current_date += timedelta(days=rest_days + 1)` = 3 days between sessions.

This creates a 3-day gap (e.g., Mon → Thu → Sun) instead of the documented 'every other day' pattern.

### Expected Behavior

3-day schedule should space sessions roughly every 2-3 days (e.g., Mon/Wed/Fri or Tue/Thu/Sat).

### Actual Behavior

Code produces 3-4 day gaps due to `rest_days + 1` arithmetic.

### Fix

Rewrite day-spacing logic to use absolute day-of-week assignments for 3-day schedule:
```python
if days_per_week == 3:
    # Mon=0, Wed=2, Fri=4 pattern
    session_days_in_week = [0, 2, 4]
```
Or use proper rest_days without +1 adjustment.

### Test Case (for verification)

Generate 1-week plan with 3 days/week starting Mon 2026-02-17.
Expected dates: Mon 2026-02-17, Wed 2026-02-19, Fri 2026-02-21.
Current bug: likely produces Mon, Thu, Sun pattern.

---

## Issue #4: Endurance session stops at sets_max regardless of total_target

**Severity**: LOW  
**Category**: LOGIC_ERROR  
**File**: `planner.py`  
**Location**: calculate_set_prescription(), E session block, line ~160-180

### Problem

The endurance ladder stops when `len(sets) < params.sets_max` is false, even if `accumulated < total_target`. This means if total_target=30 but sets_max=10, the session might only prescribe 25 reps.

### Expected Behavior

Endurance session should continue adding sets until total_target is reached or sets_max is hit.

### Actual Behavior

Loop condition uses AND instead of OR: stops when either condition fails.

### Fix

Change loop condition to:
```python
while accumulated < total_target and len(sets) < params.sets_max:
```
(This is already correct in the code, so this may be a non-issue unless sets_max is too low.)

### Test Case (for verification)

Generate E session with TM=10 (total_target=30), sets_max=10, starting reps=5.
Expected: sum(set reps) ≥ 30 or 10 sets, whichever comes first.
Verify actual behavior matches.

---

## Issue #5: Autoregulation gated at 5+ sessions but FF model needs more data

**Severity**: MEDIUM  
**Category**: PREMATURE_FEATURE  
**File**: `planner.py`  
**Location**: calculate_set_prescription(), line ~145

### Problem

Autoregulation is enabled when `history_sessions >= 5`, but the fitness-fatigue model requires ~2-3 weeks of data (6-12 sessions) to stabilize readiness_mean and readiness_var. Applying autoregulation at 5 sessions may cause wild z-score swings.

### Expected Behavior

Gate autoregulation at ≥10 sessions or ≥3 weeks of history.

### Actual Behavior

Autoregulation gate is `if history_sessions >= 5`.

### Fix

Increase threshold to 10:
```python
if history_sessions >= 10:
    adj_sets, adj_reps = apply_autoregulation(base_sets, target_reps, ff_state)
```

### Test Case (for verification)

Simulate user with 6 sessions: verify z-score is reasonable (not ±5 due to low variance).
If z-score is extreme, autoregulation will incorrectly slash volume.

---

## Issue #6: Rest normalization formula direction is backwards

**Severity**: CRITICAL  
**Category**: FORMULA_ERROR  
**File**: `metrics.py`  
**Location**: effective_reps(), line ~60

### Problem

The code computes `reps* = reps / F_rest(rest)`, but F_rest < 1 when rest < 180s.
This means short rest produces reps* > reps (e.g., 10 reps with 60s rest → 10/0.85 ≈ 11.7 'effective').

This is correct per the docs: short rest makes reps 'harder', so we give credit.

BUT: this contradicts the training_load calculation in physiology.py, which uses `rest_stress_multiplier(rest)` that is >1 for short rest. Both can't be right.

### Expected Behavior

Consistent interpretation: either short rest increases normalized reps OR increases training load, not both.

### Actual Behavior

Short rest increases both normalized reps (metrics.py) AND training load (physiology.py), double-penalizing.

### Fix

Decision required:
1. If short rest should increase 'effective difficulty' for performance tracking:    keep effective_reps as-is, remove rest_stress_multiplier from training_load.
2. If short rest should increase fatigue accumulation but not performance credit:    invert effective_reps to reps* = reps × F_rest.

Recommend option 1: short rest makes reps 'harder' for performance, neutral for load.

### Test Case (for verification)

User does 10 reps with 60s rest vs 180s rest. Compare:
- Normalized reps: should differ
- Training load: should be similar (or explicitly different if intentional)

---

## Issue #7: Grip rotation counter mutated but not returned

**Severity**: LOW  
**Category**: STATE_ERROR  
**File**: `planner.py`  
**Location**: _next_grip(), line ~230

### Problem

The function `_next_grip(session_type, counts)` modifies the `counts` dict in-place and returns the grip string. This works because Python dicts are mutable, but it's non-obvious and error-prone (caller must remember counts is modified).

### Expected Behavior

Pure function that returns (grip, new_counts) or explicit mutate-and-return pattern.

### Actual Behavior

Mutates counts in-place, returns only grip.

### Fix

Keep current implementation but add docstring clarifying mutation:
```python
def _next_grip(session_type: str, counts: dict[str, int]) -> str:
    '''Return next grip for session_type and increment counts[session_type] in-place.'''
```

### Test Case (for verification)

Verify grip rotation cycles correctly across planned sessions: S sessions should cycle pronated → neutral → supinated → pronated.

---

## Issue #8 (REVISED): Expected TM past target is OK, but plan must keep growing

**Severity**: LOW (revised from MEDIUM)  
**File**: `planner.py`  
**Status**: CLOSE / Accept current behavior with one tweak

### Clarification

It is acceptable for the user to exceed `target_max_reps`. The plan should continue developing past the target so those values are actually achievable. Do **not** cap `expected_tm` at `target_max_reps`.

### Remaining Fix

The plan generator currently caps `tm_float` at `float(target)` for prescriptions:
```python
tm_float = min(tm_float + progression, float(target))  # ← removes this cap
```
Remove the cap so prescriptions continue scaling past the target. The target should only be used for **estimating completion date**, not for limiting prescriptions.

### Test

Generate plan for user with TM=29, target=30. Verify that after week 2 the plan prescribes sessions based on TM=31, TM=32, etc., not frozen at TM=30.

---

## Issue #9: Session parameters changed from spec with inline comments claiming 'for more challenge'

**Severity**: MEDIUM  
**Category**: CONFIG_ISSUE  
**File**: `config.py`  
**Location**: SESSION_PARAMS, line ~100-180

### Problem

Config has comments like '# Increased from 0.35 for more challenge' but these changes:
- Make S (strength) sessions harder by raising reps_fraction_low from 0.35 to 0.50
- Make H (hypertrophy) rest shorter (90-150s instead of 120-180s)
These changes were not in the original spec and may cause premature failure.

### Expected Behavior

Use evidence-based defaults from training_model.md spec.

### Actual Behavior

Config deviates with ad-hoc 'challenge' adjustments.

### Fix

Revert to spec defaults:
```python
"S": SessionTypeParams(
    reps_fraction_low=0.35,
    reps_fraction_high=0.55,
    reps_min=3,
    sets_min=3,
    rest_min=180,
    rest_max=240,
),
"H": SessionTypeParams(
    rest_min=120,
    rest_max=180,
),
```

### Test Case (for verification)

User with TM=10 should get S session: 4 reps/set (35% of 10), not 5 reps (50% of 10).

---

## Issue #10: Initial readiness_var=1.0 causes extreme z-scores in early sessions

**Severity**: LOW  
**Category**: INITIALIZATION_ERROR  
**File**: `physiology.py`  
**Location**: build_fitness_fatigue_state(), line ~180

### Problem

When history is empty, FF state is initialized with readiness_var=1.0. After 1-2 sessions, readiness might be ±5 with std_dev ≈ 1.0, producing z-scores of ±5, which triggers aggressive volume reductions even though the model hasn't stabilized.

### Expected Behavior

Initialize readiness_var higher (e.g., 10.0) to prevent wild z-scores until variance converges.

### Actual Behavior

readiness_var=1.0 at init.

### Fix

```python
return FitnessFatigueState(
    readiness_var=10.0,  # Higher initial variance to dampen early z-scores
)
```

### Test Case (for verification)

Simulate user with 3 sessions. Verify z-score stays in [-2, +2] range.

---

## Issue #11 (NEW, CRITICAL): Unstable plan — regeneration overwrites past and resets week counter

**Severity**: CRITICAL  
**File**: `planner.py` → `generate_plan()`  
**Category**: ARCHITECTURE_ERROR

### Problem

When a user logs a session and the plan is regenerated, three things go wrong:

1. **Past sessions change retroactively.** The "Prescribed" column for the just-logged session shows *new* prescription values (e.g., `6x3 +1.5kg / 240s`) instead of what was *originally* prescribed when the user performed the workout. This makes logged results uninterpretable: the user completed a different workout than what now appears in the Prescribed column.

2. **The plan always restarts from session type S (Strength).** The schedule template is `S → H → T → E`, and regeneration always begins at index 0. If the user just did H on Sunday, the next session should be T (or E), not S again.

3. **Week counter resets to 1.** Every regeneration produces `Week 1, session 1/N`. The user sees perpetual "Week 1" regardless of how many weeks they've trained.

### Expected Behavior

1. **Prescribed values for past sessions are immutable.** Once a session is planned and the user trains, the original prescription is stored alongside the actual results. Regeneration must never overwrite historical prescriptions.

2. **New plan continues the schedule rotation from the last logged session.** If the last logged session was `H`, the next planned session should be `T` (in a 4-day schedule). The planner must look at the most recent session type in history and resume the cycle from the next position.

3. **Week counter is cumulative.** Track weeks from the very first session in history, not from the regeneration date.

### Fix

**A) Store original prescriptions in history (immutable).**

When a user logs a session, the `SessionResult` should include the `planned_sets` as they were at the time of planning. The history store must preserve these. Regeneration must not touch `SessionResult` records.

**B) Resume schedule rotation from history tail.**

```python
def get_next_session_type(history: list[SessionResult], schedule: list[str]) -> int:
    """Return the index into `schedule` for the next session."""
    if not history:
        return 0
    last_type = history[-1].session_type
    if last_type in schedule:
        last_idx = schedule.index(last_type)
        return (last_idx + 1) % len(schedule)
    return 0
```

Then in `generate_plan()`:
```python
schedule = get_schedule_template(days_per_week)
start_idx = get_next_session_type(history, schedule)
# rotate schedule to start from the correct position
for week in range(num_weeks):
    for i, session_type in enumerate(schedule):
        actual_type = schedule[(start_idx + i) % len(schedule)]
        ...
```

**C) Cumulative week counter.**

Calculate `week_number` from the first session in history:
```python
first_date = datetime.strptime(history[0].date, "%Y-%m-%d")
current_week = (current_date - first_date).days // 7 + 1
```

### Test Cases

1. Log sessions S, H in sequence. Regenerate plan. Verify next session is T (not S).
2. Log 3 weeks of training. Regenerate. Verify week counter shows Week 4 (not Week 1).
3. Log a session. Check that `show-history` still shows the *original* prescribed sets for that session, not new ones.
4. Log H session on Sunday with poor results. Verify Monday's plan is T or E (continuing rotation), not S.

---

## Issue #12 (NEW, HIGH): Added weight ignores bodyweight — useless for heavy trainees

**Severity**: HIGH  
**File**: `planner.py` → `calculate_set_prescription()`, `config.py`  
**Category**: FORMULA_ERROR

### Problem

Current formula:
```
added_weight = (training_max - 9) × 0.5   # capped at 10 kg
```

This produces identical added weight regardless of bodyweight:
- 45 kg person with TM=12: +1.5 kg (3.3% of BW) — meaningful
- 90 kg person with TM=12: +1.5 kg (1.7% of BW) — negligible stimulus

The added weight must be **relative to bodyweight** to provide equivalent relative overload.

### Fix

Replace with a bodyweight-relative formula. Use total pulling load (BW + added) as a percentage target:

```python
def calculate_added_weight(training_max: int, bodyweight_kg: float) -> float:
    """
    Calculate added weight for strength sessions.

    Logic: at TM=9, no added weight. As TM grows, target a progressive
    increase in total pulling load relative to bodyweight.

    Target increment per TM point above 9:
        delta_load = BW × WEIGHT_INCREMENT_FRACTION_PER_TM

    Example with BW=82kg, FRACTION=0.01:
        TM=10 → +0.82 kg (round to 1.0)
        TM=12 → +2.46 kg (round to 2.5)
        TM=15 → +4.92 kg (round to 5.0)
        TM=20 → +9.02 kg (round to 9.0)
    """
    if training_max <= 9:
        return 0.0

    points_above = training_max - 9
    raw_weight = bodyweight_kg * WEIGHT_INCREMENT_FRACTION_PER_TM * points_above
    # Round to nearest 0.5 kg (practical plate increments)
    rounded = round(raw_weight * 2) / 2
    return min(rounded, MAX_ADDED_WEIGHT_KG)
```

Add to config:
```yaml
weight_increment_fraction_per_tm: 0.01   # 1% of BW per TM point above 9
max_added_weight_kg: 20.0                # absolute cap
```

### Test Cases

| BW (kg) | TM | Current (kg) | Fixed (kg) |
|---------|-----|-------------|------------|
| 45      | 12  | 1.5         | 1.5        |
| 82      | 12  | 1.5         | 2.5        |
| 95      | 12  | 1.5         | 3.0        |
| 82      | 20  | 5.5         | 9.0        |

---

## Issue #13 (NEW, HIGH): Rest prescription is static average — ignores history and RIR

**Severity**: HIGH  
**File**: `planner.py` → `calculate_set_prescription()`, `config.py`  
**Category**: FORMULA_ERROR

### Problem

Rest is calculated as a fixed midpoint:
```python
rest = (params.rest_min + params.rest_max) // 2   # always 240s for S
```

This ignores:
- Previous session results (did user need more rest to maintain reps?)
- RIR feedback (RIR=0 means failure → next session needs more rest)
- Drop-off pattern (high drop-off with current rest → increase rest)

### Fix

Implement adaptive rest selection based on recent session data:

```python
def calculate_adaptive_rest(
    session_type: str,
    params: SessionTypeParams,
    recent_sessions: list[SessionResult],
    ff_state: FitnessFatigueState,
) -> int:
    """
    Adapt rest interval based on recent performance.

    Rules:
    1. Start at midpoint of range.
    2. If last session of same type had RIR <= 1 on any set → increase rest by 15-30s.
    3. If last session of same type had drop_off > 0.35 → increase rest by 15-30s.
    4. If readiness z-score < -1.0 → increase rest by 30s.
    5. If last session of same type had RIR >= 3 on all sets → decrease rest by 15s.
    6. Clamp to [params.rest_min, params.rest_max].
    """
    base_rest = (params.rest_min + params.rest_max) // 2

    same_type = [s for s in recent_sessions if s.session_type == session_type]
    if not same_type:
        return base_rest

    last = same_type[-1]
    adjustment = 0

    # Check RIR on last session
    rirs = [s.rir_reported for s in last.completed_sets if s.rir_reported is not None]
    if rirs and min(rirs) <= 1:
        adjustment += 30  # Failed or near-failure → more rest
    elif rirs and min(rirs) >= 3:
        adjustment -= 15  # Easy → slightly less rest

    # Check drop-off
    from .metrics import drop_off_ratio
    drop = drop_off_ratio(last)
    if drop > DROP_OFF_THRESHOLD:
        adjustment += 15

    # Check readiness
    z = ff_state.readiness_z_score()
    if z < READINESS_Z_LOW:
        adjustment += 30

    return max(params.rest_min, min(params.rest_max, base_rest + adjustment))
```

### Test Cases

1. Last S session: all sets RIR=0 → rest increases from 240s to 300s (capped).
2. Last S session: all sets RIR=3+ → rest decreases from 240s to 225s.
3. No history for this session type → default midpoint (240s for S).

---

## Issue #14 (NEW, MEDIUM): Constants must move to YAML config file

**Severity**: MEDIUM  
**File**: `config.py` → new `config.yaml` + loader  
**Category**: ARCHITECTURE

### Problem

All model constants are Python `Final` values in `config.py`. This makes them:
- Hard to edit without touching code
- Impossible to adjust from external tools (Telegram bot, web UI)
- Not self-documenting for non-Python users

### Fix

Create `config.yaml` with grouped, commented parameters. Keep `config.py` as a loader that reads YAML and exposes typed constants.

**File: `config.yaml`**
```yaml
# ─── Pull-Up Planner: Model Parameters ───────────────────────────────
# These constants control the training model's behavior.
# Adjust only if you understand their impact on plan generation.
# See docs/training_model.md for formula references.

# ── Rest Normalization ────────────────────────────────────────────────
# Controls how rest between sets affects performance estimation.
# F_rest(r) = clip((r / rest_ref_seconds) ^ gamma_rest, f_rest_min, f_rest_max)
# Higher gamma_rest → stronger penalty for short rest.
rest_normalization:
  rest_ref_seconds: 180        # Reference rest interval (seconds). Standard comparison baseline.
  gamma_rest: 0.20             # Exponent. Range [0.10–0.30]. Higher = more penalty for short rest.
  f_rest_min: 0.80             # Floor. Prevents over-crediting very short rest.
  f_rest_max: 1.05             # Ceiling. Prevents over-crediting very long rest.
  rest_min_clamp: 30           # Absolute minimum rest (seconds) to avoid math issues.

# ── Bodyweight Normalization ──────────────────────────────────────────
# Adjusts reps for bodyweight differences.
# reps** = reps* × (total_load / bw_ref) ^ gamma_bw
# gamma_bw=1.0 means linear relationship; >1.0 amplifies BW effect.
bodyweight:
  gamma_bw: 1.0                # Exponent. Range [0.8–1.2]. Higher = more BW sensitivity.

# ── Grip Normalization ────────────────────────────────────────────────
# Multiplier to normalize different grips to pronated baseline.
# Values close to 1.0. Adjust only with strong evidence.
grip_factors:
  pronated: 1.00
  neutral: 1.00
  supinated: 1.00

# ── EWMA Max Estimation ──────────────────────────────────────────────
# Controls how quickly the estimated max responds to new observations.
# M_hat(t) = (1-alpha) × M_hat(t-1) + alpha × M_obs(t)
ewma:
  alpha_mhat: 0.25             # Smoothing factor. Range [0.15–0.40]. Higher = faster response.
  beta_sigma: 0.15             # Variance smoothing. Range [0.10–0.25].
  initial_sigma_m: 1.5         # Initial uncertainty (reps). Higher = more conservative early.

# ── Fitness-Fatigue Model (Banister) ──────────────────────────────────
# Two-timescale impulse response model.
# G(t) = G(t-1) × e^(-1/tau_fitness) + k_fitness × w(t)
# H(t) = H(t-1) × e^(-1/tau_fatigue) + k_fatigue × w(t)
# Readiness R(t) = G(t) - H(t)
fitness_fatigue:
  tau_fatigue: 7.0             # Fatigue decay (days). Range [5–9]. Lower = faster fatigue recovery.
  tau_fitness: 42.0            # Fitness decay (days). Range [30–50]. Higher = longer adaptation retention.
  k_fatigue: 1.0               # Fatigue gain per unit load. Range [0.5–2.0].
  k_fitness: 0.5               # Fitness gain per unit load. Range [0.05–1.0]. Must be < k_fatigue.
  c_readiness: 0.02            # Readiness → max adjustment factor. Range [0.01–0.03].
  initial_readiness_var: 10.0  # Initial readiness variance (high to dampen early z-scores).

# ── Training Load Calculation ─────────────────────────────────────────
# w(t) = Σ(HR_j × S_rest_j × S_load_j × S_grip_j)
# HR_j = reps × E_rir(rir), where E_rir = 1 + a_rir × max(0, 3 - rir)
training_load:
  a_rir: 0.15                  # Effort multiplier per RIR below 3. Range [0.10–0.25].
  gamma_s: 0.15                # Rest stress exponent. Range [0.10–0.25].
  s_rest_max: 1.5              # Maximum rest stress multiplier.
  gamma_load: 1.5              # Added load stress exponent. Range [1.0–2.0].
  grip_stress:
    pronated: 1.00
    neutral: 0.95
    supinated: 1.05

# ── Within-Session Fatigue ────────────────────────────────────────────
# reps_pred = (p - RIR) × e^(-lambda × (j-1)) × Q_rest(r)
# Q_rest(r) = 1 - q × e^(-r / tau_r)
session_fatigue:
  lambda_decay: 0.08           # Intra-session decay rate. Range [0.05–0.12].
  q_rest_recovery: 0.3         # Recovery parameter. Range [0.2–0.4].
  tau_rest_recovery: 60.0      # Recovery time constant (seconds).
  drop_off_threshold: 0.35     # High drop-off flag. Range [0.25–0.45].

# ── Volume Targets ────────────────────────────────────────────────────
volume:
  weekly_hard_sets_min: 8      # Floor for weekly pull-up hard sets.
  weekly_hard_sets_max: 20     # Ceiling for weekly pull-up hard sets.
  weekly_volume_increase_rate: 0.10   # Max weekly increase (10%).
  deload_volume_reduction: 0.40       # Volume cut during deload (40%).

# ── Training Max ──────────────────────────────────────────────────────
training_max:
  tm_factor: 0.90              # TM = floor(factor × test_max). Always < 1.0.

# ── Session Type Parameters ───────────────────────────────────────────
# reps_fraction_low/high: fraction of TM for target reps range.
# These are clamped to [reps_min, reps_max].
session_types:
  S:  # Strength
    reps_fraction_low: 0.35
    reps_fraction_high: 0.55
    reps_min: 3
    reps_max: 6
    sets_min: 3
    sets_max: 5
    rest_min: 180
    rest_max: 300
    rir_target: 2
  H:  # Hypertrophy
    reps_fraction_low: 0.55
    reps_fraction_high: 0.75
    reps_min: 6
    reps_max: 12
    sets_min: 4
    sets_max: 6
    rest_min: 120
    rest_max: 180
    rir_target: 2
  E:  # Endurance / Density
    reps_fraction_low: 0.35
    reps_fraction_high: 0.55
    reps_min: 3
    reps_max: 8
    sets_min: 5
    sets_max: 8
    rest_min: 45
    rest_max: 90
    rir_target: 3
  T:  # Technique
    reps_fraction_low: 0.20
    reps_fraction_high: 0.40
    reps_min: 2
    reps_max: 4
    sets_min: 4
    sets_max: 8
    rest_min: 60
    rest_max: 120
    rir_target: 5
  TEST:  # Max test
    reps_fraction_low: 1.0
    reps_fraction_high: 1.0
    reps_min: 1
    reps_max: 50
    sets_min: 1
    sets_max: 1
    rest_min: 180
    rest_max: 300
    rir_target: 0

# ── Weekly Schedule ───────────────────────────────────────────────────
schedule:
  three_days: ["S", "H", "E"]
  four_days: ["S", "H", "T", "E"]
  day_spacing:
    S: 1
    H: 1
    E: 1
    T: 0
    TEST: 2

# ── Progression ───────────────────────────────────────────────────────
# delta_per_week = delta_min + (delta_max - delta_min) × (1 - TM/target)^eta
# Lower eta = more linear; higher eta = more aggressive slowdown near target.
progression:
  target_max_reps: 30
  delta_progression_min: 0.3   # Min reps/week near target.
  delta_progression_max: 1.0   # Max reps/week at low TM.
  eta_progression: 1.5         # Nonlinear exponent. Range [1.0–2.0].

# ── Plateau & Deload ─────────────────────────────────────────────────
plateau:
  plateau_slope_threshold: 0.05     # reps/week. Below this = flat.
  plateau_window_days: 21           # Days without new PR to confirm plateau.
  trend_window_days: 21             # Window for trend regression.
  fatigue_z_threshold: -0.5         # Z-score triggering concern.
  underperformance_threshold: 0.10  # 10% below predicted = underperformance.
  compliance_threshold: 0.70        # Below this = plan too hard.

# ── Readiness Gating ─────────────────────────────────────────────────
readiness:
  z_low: -1.0                  # Below this: reduce volume.
  z_high: 1.0                  # Above this: allow progression.
  volume_reduction: 0.30       # Reduce by 30% when z < z_low.

# ── Plan Horizon ──────────────────────────────────────────────────────
plan_horizon:
  min_plan_weeks: 2
  max_plan_weeks: 52
  default_plan_weeks: 4
  expected_weeks_per_rep: 2.0

# ── Added Weight (Strength sessions) ─────────────────────────────────
# Weight is relative to bodyweight for equivalent stimulus across body sizes.
# added_weight = BW × fraction_per_tm × (TM - threshold)
# Rounded to nearest 0.5 kg.
added_weight:
  tm_threshold: 9                      # TM must exceed this before adding weight.
  weight_increment_fraction_per_tm: 0.01  # 1% of BW per TM point above threshold.
  max_added_weight_kg: 20.0            # Absolute cap (kg).

# ── Autoregulation Gate ──────────────────────────────────────────────
autoregulation:
  min_sessions_for_autoreg: 10  # Need at least this many sessions before enabling autoreg.
```

**File: `config.py` (loader)**
```python
import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"
_config: dict | None = None

def _load():
    global _config
    if _config is None:
        with open(_CONFIG_PATH) as f:
            _config = yaml.safe_load(f)
    return _config

def get(section: str, key: str, default=None):
    cfg = _load()
    return cfg.get(section, {}).get(key, default)
```

### Test

1. Delete `config.yaml` → application must raise clear error with path.
2. Edit `tau_fatigue` from 7 to 14 in YAML → verify plan changes accordingly.
3. All existing tests must pass with default YAML values.

---

## Issue #15 (NEW, MEDIUM): Explanation view shows contradictory TM values

**Severity**: MEDIUM  
**File**: `planner.py` → `explain_plan_entry()`  
**Category**: DISPLAY_ERROR

### Problem (from user-provided explanation output)

The explanation says:
```
TRAINING MAX: 12
  Latest TEST: 12 reps on 2026-02-18.
  Starting TM = floor(0.9 × 12) = 10.
  No weekly progression yet (first week of plan).
  → TM for this session: int(12.00) = 12.
```

This is self-contradictory:
- Line 1: "Starting TM = floor(0.9 × 12) = 10" (correct per formula)
- Line 2: "TM for this session: int(12.00) = 12" (contradicts the above)

The explanation reveals the Issue #1 bug: the code calculates TM=10 correctly but then overrides it with the raw test max 12. The user sees both values and is confused.

### Fix

After fixing Issue #1 (use TM=floor(0.9×test_max) consistently), update the explanation to show only the correct value:
```
TRAINING MAX: 10
  Latest TEST: 12 reps on 2026-02-18.
  TM = floor(0.9 × 12) = 10.
  Weekly progression: +0.63 reps/week applied at week boundaries.
  → TM for this session: 10.
```

### Test

Run `explain` for first session after a TEST of 12. Verify all TM references show 10, not 12.

---

## Issue #16 (NEW, LOW): Progression applied intra-week via "fraction" is confusing and incorrect

**Severity**: LOW  
**File**: `planner.py` → `generate_plan()` inner loop  
**Category**: LOGIC_ERROR

### Problem

The explanation shows:
```
EXPECTED TM AFTER: 12
  Session 1/4 in week → fraction = 0.25.
  Progression rate at TM 12: 0.63 reps/week.
  Δ TM = 0.63 × 0.25 = 0.16 reps.
```

This fractional intra-week progression is meaningless:
- TM is an integer, so 0.16 reps rounds to 0 → no actual change.
- It implies progression happens continuously within a week, which is physically nonsensical. Adaptation happens between sessions, not proportionally to session index.

### Fix

Apply progression **once per week** (at the start of each new week), not fractionally per session. Remove the `week_fraction` math entirely. Expected TM for all sessions in the same week should be the same value.

### Test

Generate 1-week plan (4 sessions). Verify all 4 sessions show the same `expected_tm`.

---

## Updated Priority Order

1. **Issue #11** (CRITICAL) — Plan instability: schedule reset, week reset, retroactive prescription changes
2. **Issue #2** (CRITICAL) — Weekly progression applied per session (from v1 list)
3. **Issue #6** (CRITICAL) — Rest normalization double-counting (from v1 list)
4. **Issue #12** (HIGH) — Added weight ignores bodyweight
5. **Issue #13** (HIGH) — Rest prescription is static average
6. **Issue #1** (HIGH) — TM bypasses TM_FACTOR (from v1 list)
7. **Issue #15** (MEDIUM) — Contradictory TM in explanation view
8. **Issue #14** (MEDIUM) — Constants → YAML config file
9. **Issue #16** (LOW) — Intra-week fractional progression is meaningless
10. **Issue #8** (LOW, revised) — Remove TM cap at target

---

### Issue #17 — NEW, LOW: Endurance total reps formula too simplistic

**File**: `planner.py` → `calculate_set_prescription()` E block

**Problem**: `total_target = training_max * 3` is a flat multiplier. The spec says `kE * TM` where kE grows with level (3.0 → 5.0).

**Fix**:
```python
def endurance_volume_multiplier(tm: int) -> float:
    """kE grows from 3.0 to 5.0 as TM increases from 5 to 30."""
    return 3.0 + 2.0 * min(1.0, max(0.0, (tm - 5) / 25))
```

**Test**: TM=5 → total=15, TM=15 → total=45, TM=30 → total=150.

---

### Issue #18 — NEW, LOW: models.py `SessionPlan.__post_init__` has unreachable validation

**File**: `models.py`

**Problem**: In `SessionPlan.__post_init__`, the `total_reps` property is defined, then grip/session_type validation follows, but this code is *after* the `return` of `__post_init__` (implicit). The property body and the validation lines are at the same indentation, causing the validation to be unreachable class-level code.

**Fix**: Move grip and session_type validation above the property definition:
```python
def __post_init__(self):
    SessionResult._validate_date(self.date)
    if self.grip not in ("pronated", "supinated", "neutral"):
        raise ValueError(f"Invalid grip: {self.grip}")
    if self.session_type not in ("S", "H", "E", "T", "TEST"):
        raise ValueError(f"Invalid session_type: {self.session_type}")
```

**Test**: `SessionPlan(date="2026-02-23", grip="invalid", ...)` must raise ValueError.

---

<a name="per-user-settings"></a>
## Part 2: Per-User Settings (stored in `data/profile.json`)

These are user-editable settings (not model constants). They live in the user's profile, not in `config.yaml`.

```json
{
  "height_cm": 175,
  "sex": "male",
  "current_bodyweight_kg": 82.0,
  "preferred_days_per_week": 4,
  "target_max_reps": 30,
  "preferred_training_days": ["mon", "wed", "fri", "sat"],
  "available_equipment": {
    "horizontal_bar": true,
    "parallel_grip_bar": true,
    "low_bar": true,
    "bench": true,
    "dumbbells_max_kg": 36,
    "weight_belt": true
  },
  "injury_notes": "",
  "preferred_grip_order": ["pronated", "neutral", "supinated"],
  "max_session_duration_minutes": 60,
  "rest_preference": "normal"
}
```

### Per-user settings description

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `height_cm` | int | required | Height in cm. Used for documentation only (currently). |
| `sex` | str | "male" | "male" or "female". May affect future recovery heuristics. |
| `current_bodyweight_kg` | float | required | Current bodyweight. Updated via `update-weight`. Affects added weight calculation and normalization. |
| `preferred_days_per_week` | int | 3 | 3 or 4. Determines schedule template (S-H-E or S-H-T-E). |
| `target_max_reps` | int | 30 | Goal. Used for estimating plan duration and completion date. Plan continues past this value. |
| `preferred_training_days` | list[str] | null | If set, planner assigns sessions to these weekdays. If null, uses default patterns (Mon/Wed/Fri or Mon/Tue/Thu/Sat). |
| `available_equipment` | dict | all true | Controls which accessories are prescribed. If `weight_belt=false`, no weighted pull-ups. |
| `max_session_duration_minutes` | int | 60 | Soft cap. Planner estimates session time from sets × (reps_time + rest) and may reduce sets if too long. |
| `rest_preference` | str | "normal" | "short" / "normal" / "long". Shifts rest range selection within the allowed [min, max] per session type. |

**CLI commands**:
- `pullup-planner profile` — show current profile.
- `pullup-planner profile --set days_per_week=3` — update setting.
- `pullup-planner update-weight 80.5` — shortcut for bodyweight.

---

<a name="adaptation-timelines"></a>
## Part 3: User Guide — What Adapts and When

This section must be shown to the user on first run (`init`) and available via `pullup-planner help adaptation`.

### How the planner learns from your data

This planner is adaptive: it improves its prescriptions as you log more sessions. Here is what you can expect at each stage.

#### Day 1 (no history)
- You provide your baseline max and bodyweight.
- Plan uses conservative defaults: moderate volume, standard rest, no weighted pull-ups until TM > 9.
- **What the model knows**: almost nothing. Prescriptions are safe but generic.

#### After 1–2 weeks (3–8 sessions)
- The EWMA max estimate (M_hat) starts tracking your actual performance.
- Rest normalization begins working: if you log short-rest sessions, the model recognizes that 8 reps @ 60s rest is harder than 8 reps @ 180s rest.
- **What the model knows**: rough estimate of your max, basic performance trend.
- **What it cannot do yet**: autoregulate volume (too little data for stable readiness scores).

#### After 3–4 weeks (10–16 sessions)
- **Autoregulation activates** (requires ≥10 sessions). The fitness-fatigue model now has enough data to compute meaningful readiness z-scores.
- Plateau detection becomes possible (needs ≥2 TEST sessions in a 21-day window).
- Rest adaptation kicks in: if your recent sessions show RIR=0 or high drop-off, rest increases.
- **What the model knows**: your fatigue pattern, recovery rate, performance trend, and compliance.

#### After 6–8 weeks (24–32 sessions)
- The within-session fatigue coefficient (lambda_decay) has enough data to fit accurately. Set-to-set predictions improve.
- Bodyweight trend tracking is meaningful if you've logged BW changes.
- Deload triggers become reliable (plateau + fatigue correlation is detectable).
- **What the model knows**: your individual recovery profile, realistic progression rate, optimal session type distribution.

#### After 12+ weeks (48+ sessions)
- Long-term fitness (tau_fitness = 42 days) has accumulated enough history to reflect true adaptation.
- The model can detect whether your progression rate is above or below the expected nonlinear curve, and adjust plan horizon accordingly.
- **What the model knows**: your full training profile. This is when the model is most accurate.

### Practical advice for best results

1. **Log every session** — even bad ones. RIR=0 and incomplete sessions are valuable data.
2. **Log rest times** — even approximate. The model treats "unknown rest" as 180s, which may be wrong.
3. **Do a TEST session every 2–3 weeks** — this anchors the max estimate. Without TEST sessions, the model relies on inference from working sets (less accurate).
4. **Update bodyweight when it changes** — even 1-2 kg matters for normalization and added weight calculation.
5. **Don't panic if the plan adjusts** — after logging, the next session's prescription may change. Past sessions will not change (their prescriptions are frozen).
6. **Trust the deload** — if the planner recommends a deload week, take it. Fighting through fatigue leads to plateau.

---

<a name="generalizability"></a>
## Part 4: Can This Model Be Used for Other Exercises?

**Short answer**: Yes, with minor adaptations. The core architecture (fitness-fatigue model, EWMA max tracking, autoregulation, periodization) is exercise-agnostic. What changes is the load definition and normalization.

### What is universal (works for any exercise)

| Component | Universality | Notes |
|-----------|-------------|-------|
| Fitness-fatigue impulse response (Banister) | Fully universal | Originally designed for endurance sports, validated across swimming, cycling, running, weightlifting. The model tracks "performance = fitness − fatigue" regardless of movement. |
| EWMA max estimation | Fully universal | Smoothed estimate of current capacity. Works for any measurable performance metric (reps, load, time). |
| RIR/RPE autoregulation | Fully universal | RPE and RIR scales are validated for squat, bench press, deadlift, pull-ups, and bodyweight movements. The scale itself is exercise-agnostic. |
| Set-decay model (within-session fatigue) | Fully universal | `reps_pred = (p - RIR) × e^(-λ×(j-1)) × Q_rest(r)` applies to any rep-based exercise. Lambda may differ per exercise. |
| Compliance and plateau detection | Fully universal | Trend slopes and compliance ratios are dimensionless. |
| Rest normalization | Fully universal | Rest intervals affect all exercises similarly (short rest = less recovery = fewer reps next set). |
| Periodization (S/H/E session types) | Fully universal | DUP (daily undulating periodization) is validated for barbell, bodyweight, and machine exercises. |

### What requires adaptation per exercise class

| Exercise class | Load definition | BW normalization | Key change needed |
|---------------|----------------|------------------|-------------------|
| **Pull-ups** (current) | `total_load = BW + added_weight` | Yes, BW is the primary load | Current implementation |
| **Push-ups** | `total_load = ~0.64 × BW + added_weight` | Yes, but only ~64% of BW is lifted | Add `bw_fraction` config per exercise (0.64 for push-ups) |
| **Dips** | `total_load = BW + added_weight` | Yes, full BW like pull-ups | Nearly identical to pull-ups; reuse current model |
| **Barbell bench press** | `total_load = bar_weight` | No BW component | Set `bw_fraction = 0.0`; load is entirely external |
| **Barbell squat** | `total_load = bar_weight` | No BW component (BW is already supporting) | Set `bw_fraction = 0.0` |
| **Dumbbell curls** | `total_load = dumbbell_weight` | No BW component | Set `bw_fraction = 0.0`; Epley 1RM works normally |
| **Inverted rows** | `total_load = ~0.5–0.7 × BW` | Partial BW | Add `bw_fraction` config |

### Minimal code changes for multi-exercise support

1. **Add `exercise_config` to YAML**:
```yaml
exercises:
  pull_up:
    bw_fraction: 1.0
    primary_grip: pronated
    epley_applicable: true
    default_rest_ref: 180
  push_up:
    bw_fraction: 0.64
    primary_grip: null
    epley_applicable: true
    default_rest_ref: 120
  bench_press:
    bw_fraction: 0.0
    primary_grip: null
    epley_applicable: true
    default_rest_ref: 180
  dumbbell_curl:
    bw_fraction: 0.0
    primary_grip: null
    epley_applicable: true
    default_rest_ref: 120
```

2. **Modify `bodyweight_normalized_reps()`**:
```python
def bodyweight_normalized_reps(reps, session_bw, ref_bw, added_load, bw_fraction=1.0):
    total_load = session_bw * bw_fraction + added_load
    ref_load = ref_bw * bw_fraction if bw_fraction > 0 else added_load
    l_rel = total_load / ref_load if ref_load > 0 else 1.0
    return reps * (l_rel ** GAMMA_BW)
```

3. **Modify training load calculation** similarly.

4. **Session type templates** can be reused as-is (S/H/E/T are universal concepts).

### What does NOT transfer without deeper changes

- **Grip rotation**: specific to pull-ups/chin-ups. Other exercises don't have grip variants (or have different ones like bench grip width).
- **Accessory prescriptions**: exercise-specific. Pull-up accessories (inverted rows, scapular holds) don't apply to bench press.
- **The "30 reps" goal structure**: is a bodyweight-endurance target. For barbell exercises, the goal would be a 1RM or a rep target at a fixed weight, requiring a different plan-horizon formula.

### Verdict

The core engine (fitness-fatigue, EWMA, autoregulation, set-decay, periodization, rest normalization) is **90% reusable**. The only exercise-specific piece is the `bw_fraction` multiplier and the accessory library. To make the app multi-exercise, add an `exercise_config` section to YAML and parameterize `bw_fraction` — the rest of the math stays identical.

---

## Implementation Notes

- Fix issues in the order listed (Critical → High → Medium → Low).
- After each fix, run `pytest` and verify no regressions.
- The YAML migration (Issue #14) should be done early because many other fixes reference YAML keys.
- The per-user settings (Part 2) and adaptation guide (Part 3) can be implemented in parallel with bug fixes.
- The generalizability analysis (Part 4) is informational only — no code changes required now, but the architecture should not make multi-exercise support harder.

---