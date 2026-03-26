# Performance Formulas: Volume and 1RM

This document describes the user-facing performance metrics exposed by the API.

---

## Shared definitions

```
BW           = bodyweight (kg)
bw_fraction  = exercise-specific coefficient (pull_up=1.0, dip=0.92, bss=0.71,
                incline_db_press=0.0)
assistance_kg = kg of assistance from bands/machine (0 for unassisted)
L_eff        = bw_fraction × BW + added_weight_kg − assistance_kg  — effective working load
```

`compute_leff(bw_fraction, bodyweight_kg, added_weight_kg, assistance_kg)` is the public
helper that computes L_eff.  For exercises where the user's bodyweight contributes nothing
(e.g. incline dumbbell press, bw_fraction = 0), L_eff equals the dumbbell weight alone.

---

## 1. Volume metrics

### Per-set

```
volume_set = L_eff × reps
```

### Session total

```
volume_session = Σ (L_eff × reps)   (sum over all completed sets)
```

### Average per set

```
avg_volume_set = volume_session / n_sets
```

### Interpretation

Volume in kg·reps makes load and effort comparable across sessions with different
weights and rep counts.  A session of 4 × 8 reps at L_eff = 90 kg gives
`volume_session = 2880 kg·reps`.

---

## 2. 1RM estimation

**Question: "How strong am I right now?"**

The 1RM for any completed set (or a planned / goal set) is estimated using a
rep-range-aware blend of formulas for best accuracy:

| Rep range | Formulas blended | Best for |
|---|---|---|
| r ≤ 5 | avg(Brzycki, Lander) | Near-maximal strength sets |
| 6 ≤ r ≤ 10 | avg(Brzycki, Lander, Epley) | Moderate hypertrophy range |
| 11 ≤ r ≤ 20 | avg(Lombardi, Epley) | Higher rep / endurance sets |
| r > 20 | None (unreliable) | — |

The formulas operate on `L_eff` (not raw added weight) and return the estimated 1RM
in the same `L_eff` units:

```
epley_1rm    = L_eff × (1 + r / 30)
brzycki_1rm  = L_eff / (1.0278 − 0.0278 × r)
lander_1rm   = 100 × L_eff / (101.3 − 2.67123 × r)
lombardi_1rm = L_eff × r ^ 0.10
```

For a session, the **best** 1RM estimate across all sets is reported
(the set that yields the highest estimate).

---

## API reference

### Goal metrics

```python
from bar_scheduler.api import get_goal_metrics

prog = get_goal_metrics(data_dir, "pull_up")
# → {
#     "goal_reps": 12,              # int | None
#     "goal_weight_kg": 0.0,        # float | None  — added weight at goal
#     "goal_leff": 80.0,            # float | None  — L_eff at goal
#     "estimated_1rm": 109.3,       # float | None  — 1RM implied by achieving goal
#     "volume_set": 960.0,          # float | None  — L_eff × goal_reps (one goal set)
# }
```

All fields are `None` when no goal has been set via `set_exercise_target`.

`estimated_1rm` answers: "What 1RM would I have **if** I could do `goal_reps` at
`goal_weight`?" — computed from `(goal_leff, goal_reps)` using the best formula for
that rep range.

### History and plan sessions

Each history record returned by `get_history()` and each session in `get_plan()["sessions"]`
includes a `session_metrics` dict:

```python
s["session_metrics"]
# → {
#     "volume_session": 1280.0,    # float  — Σ(L_eff × reps) over all completed sets
#     "avg_volume_set": 640.0,     # float  — volume_session / n_sets
#     "estimated_1rm": 101.7,      # float | None  — best 1RM estimate across all sets
# }
```

For **history** sessions: metrics are computed once at log time (`log_session`) and
stored in the JSONL file.  Sessions logged before this feature was introduced return
`None` for all three fields.

For **planned** sessions: metrics are computed from the prescription (target reps and
added weight) using the current bodyweight.

---

## Internal model (unchanged)

The Banister fitness-fatigue model (`physiology.py`) still uses `w(t)` internally
to compute `fitness`, `fatigue`, `readiness_z_score`, and `deload_recommended`
in `get_training_status()`.  These are not exposed as volume metrics — they are
distinct internal signals for plan autoregulation.
