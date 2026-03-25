# Performance Formulas: EBR, Capability, and Progress

This document describes the three user-facing metrics that replace the internal
Banister training-load value in the public API.

---

## Why not just show "load"?

The internal Banister load (`w(t)`) is correct for fitness-fatigue modeling, but
confusing as a user-facing number because:

- It uses an RIR assumption (default 2) that makes goal load numerically smaller
  than test load even when the goal is objectively harder.
- It conflates effort level, rep count, and weight into one number with no
  intuitive anchor.
- Comparing "Load = 19 (goal)" to "Load = 26 (test)" implies the goal is easier,
  which is wrong.

The three metrics below each answer exactly one question and are independent of
each other.

---

## Shared definitions

```
BW           = bodyweight (kg)
bw_fraction  = exercise-specific coefficient (pull_up=1.0, dip=0.92, bss=0.71,
                incline_db_press=0.0)
L_eff        = bw_fraction × BW + added_weight_kg  — effective working load
load_ratio   = L_eff / BW                          — load relative to bodyweight
```

---

## 1. EBR — Equivalent Bodyweight Reps (volume metric)

**Question: "How hard was this session?"**

### Per-set formula

```
rest_penalty = max(1.0, 1 + REST_RHO × exp(-(rest_sec − 20) / REST_TAU))
EBR_set      = reps × (load_ratio ^ EBR_ALPHA) × rest_penalty
```

Rules:
- **First set** of a session: `rest_penalty = 1.0` (fresh state, no penalty)
- Short rest (< 60 s) increases rest_penalty → EBR_set increases → session
  counts as harder even with the same reps and weight
- Heavier weight raises `load_ratio^EBR_ALPHA` nonlinearly: doubling the load
  more than doubles the EBR per rep

### Session total

```
EBR_session = Σ EBR_set           (sum over all completed sets)
kg_eq       = BW × EBR_session   (absolute equivalent in kg-reps)
```

`kg_eq` allows comparison across users with different bodyweights.

### Default config (in `exercises.yaml`, section `ebr_metric`)

| Constant | Default | Meaning |
|---|---|---|
| `EBR_ALPHA` | 1.6 | Load nonlinearity exponent |
| `REST_TAU` | 90.0 s | Rest decay time constant |
| `REST_RHO` | 0.25 | Rest penalty amplitude |
| `EBR_BASE` | 1.0 | Progress formula anchor |

### Interpretation

> **1 EBR ≈ 1 rep at bodyweight, well-rested**

| EBR range | What it looks like (pull-up, BW=80 kg) |
|---|---|
| 5–8 | 1 short set (3–5 reps) |
| 15–25 | Moderate session (3–4 sets × 5–8 reps) |
| 40–60 | Hard session with added weight or many sets |

### Worked example

Pull-up, BW=80 kg, session: 5 reps / 4 reps / 3 reps, rest=180 s between sets

```
set 0 (first): rest_penalty=1.0, L_eff=80, load_ratio=1.0
  EBR = 5 × 1.0^1.6 × 1.0 = 5.00

set 1: rest_penalty = 1 + 0.25×exp(-160/90) ≈ 1.042
  EBR = 4 × 1.0 × 1.042 = 4.17

set 2: same penalty
  EBR = 3 × 1.0 × 1.042 = 3.13

EBR_session = 12.30   kg_eq = 984
```

---

## 2. Capability — current strength estimate

**Question: "How strong am I right now?"**

```
one_rm_leff = max over all history: L_eff × (1 + reps / 30)   [Epley 1RM]
```

This is the best effective-load 1RM estimate from all historical sessions (TEST
and training). Weighted sets naturally yield higher estimates because their L_eff
is larger.

`one_rm_leff` is expressed in kg (effective load). To project **max reps at any
target weight**, use the Epley inverse (see Progress section below).

---

## 3. Progress % — nonlinear goal proximity

**Question: "How close am I to my goal?"**

### Computing max reps at goal weight

```
goal_leff        = bw_fraction × BW + goal_weight_kg
max_reps_at_goal = max(0, 30 × (one_rm_leff / goal_leff − 1))   [Epley inverse]
```

This gives the **concrete, readable number**: "You can currently do ~6 reps at
+25 kg."

### Log-based progress formula

```
progress = clamp(log(max_reps_at_goal / EBR_BASE) / log(goal_reps / EBR_BASE), 0, 1)
progress_pct = progress × 100
```

With `EBR_BASE = 1.0` this simplifies to:

```
progress_pct = 100 × ln(max_reps_at_goal) / ln(goal_reps)   (when 1 ≤ max_reps < goal_reps)
```

### Why log scale?

Strength adaptation follows a power-law curve (Newell & Rosenbloom, 1981): early
gains are large and fast; gains near the ceiling are small and slow.

Linear progress (`6/12 = 50%`) overstates how far you have to go. Going from 1 rep
to 6 reps at a given weight requires far more strength adaptation than going from 6
to 12 reps. The log scale captures this correctly:

| Max reps now | Goal reps | Linear % | Log % |
|---|---|---|---|
| 1 | 12 | 8% | 0% |
| 3 | 12 | 25% | 44% |
| 6 | 12 | 50% | 72% |
| 9 | 12 | 75% | 88% |
| 12 | 12 | 100% | 100% |

### Difficulty ratio

```
difficulty_ratio = EBR_goal / EBR_cap_at_goal
```

- `= 1.0` → goal is exactly at current capability
- `> 1.0` → goal is harder than current level (e.g. 1.5 = 50% more demanding)
- `< 1.0` → goal already exceeded

### Worked example

User: BW=80 kg, can do 12 pull-ups max → `one_rm_leff = 80 × (1 + 12/30) = 112 kg`

Goal: 12 dips @ +25 kg added weight

```
goal_leff        = 80×0.92 + 25 = 98.6 kg
max_reps_at_goal = 30 × (112/98.6 − 1) = 30 × 0.136 = 4.1 reps
progress_pct     = 100 × ln(4.1) / ln(12) = 100 × 1.411 / 2.485 = 56.8%
difficulty_ratio = (12 × (98.6/80)^1.6) / (4.1 × (98.6/80)^1.6) = 12/4.1 ≈ 2.93
```

**Meaning**: "You can currently do ~4 reps at +25 kg dips. Your goal is 12 reps.
You are 57% of the way there. The goal is 2.9× harder than your current level."

---

## API reference

```python
from bar_scheduler.api import get_ebr_data, get_goal_progress, compute_set_ebr

# Per-session EBR history + projected plan
data = get_ebr_data(data_dir, "dip", weeks_ahead=4)
# → {"history": [{"date", "session_type", "ebr", "kg_eq"}, ...],
#    "plan":    [{"date", "session_type", "ebr", "kg_eq"}, ...]}

# Current capability and progress toward goal
prog = get_goal_progress(data_dir, "dip")
# → {
#     "one_rm_leff": 112.0,          # best Epley 1RM (effective kg)
#     "capability_ebr": 1.98,        # EBR of one rep at 1RM
#     "goal_reps": 12,
#     "goal_weight_kg": 25.0,
#     "goal_ebr": 16.76,             # EBR of hitting the goal exactly
#     "max_reps_at_goal": 4.1,       # predicted reps at goal weight NOW
#     "progress_pct": 56.8,          # 0–100, nonlinear log scale
#     "difficulty_ratio": 2.93,      # how much harder goal is vs. now
#   }

# EBR for a single hypothetical set
ebr = compute_set_ebr(data_dir, "dip", reps=12, added_weight_kg=25.0)
# → float (EBR contribution of this set at well-rested, neutral conditions)
```

---

## Internal model (unchanged)

The Banister fitness-fatigue model (`physiology.py`) still uses `w(t)` internally
to compute `fitness`, `fatigue`, `readiness_z_score`, and `deload_recommended`
in `get_training_status()`. These are not exposed as EBR — they are distinct
internal signals for plan autoregulation.
