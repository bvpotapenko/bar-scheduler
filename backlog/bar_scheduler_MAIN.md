# Pull-Up Planner → Multi-Exercise Planner: Consolidated Task List (v4-final)

**Date**: 2026-02-23  
**Audience**: Coding agent  
**Supersedes**: All previous fix lists (v1, v2, v3)

---

## Table of Contents

1. [Architecture: Multi-exercise extraction](#architecture)
2. [Exercise definitions: Pull-ups, Dips, Bulgarian Split Squat](#exercise-defs)
3. [1RM display feature](#1rm-feature)
4. [Assessment test protocols (per exercise)](#assessment)
5. [Consolidated fix list (all issues, priority order)](#fixes)
6. [Per-user settings](#per-user)
7. [User guide: adaptation timelines](#adaptation)
8. [Documentation requirements](#docs)

---

<a name="architecture"></a>
## 1. Architecture: Multi-Exercise Extraction

### 1.1 Core principle

The planner must support **multiple exercise types** with:
- **Separate plans** per exercise (no cross-exercise fatigue calculation).
- **Shared core engine** (fitness-fatigue model, EWMA, periodization, autoregulation).
- **Per-exercise configuration** (BW fraction, grip variants, session archetypes, accessories).

### 1.2 Required refactoring

#### A) Exercise registry (`core/exercises/`)

Create an exercise registry where each exercise is defined by a configuration object:

```text
src/pullup_planner/ → src/bar_scheduler/
  core/
    exercises/
      __init__.py
      base.py          # ExerciseDefinition 
      pull_up.py
      dip.py
      bulgarian_squat.py
    engine/
      config_loader.py  # YAML → typed config
      metrics.py        # Pure functions (unchanged, parameterized)
      physiology.py     # FF model (unchanged, parameterized)
      adaptation.py     # Plateau/deload (unchanged)
      planner.py        # Plan generator (parameterized by ExerciseDefinition)
      ascii_plot.py
    models.py           # Shared dataclasses
  io/
    history_store.py    # Stores history PER exercise (separate JSONL files)
    serializers.py
  cli/
    main.py
    views.py
  exercises.yaml        # All exercise configs in one file
```

#### B) `ExerciseDefinition` base class

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ExerciseDefinition:
    """Base configuration for any exercise the planner can manage."""

    # Identity
    exercise_id: str                    # e.g., "pull_up", "dip", "bss"
    display_name: str                   # e.g., "Pull-Up", "Parallel Bar Dip"
    muscle_group: str                   # e.g., "upper_pull", "upper_push", "lower"

    # Load model
    bw_fraction: float                  # Fraction of BW that is the load (1.0 for pull-ups, 0.0 for curls)
    load_type: Literal["bw_plus_external", "external_only"]

    # Movement variants (equivalent to "grips" for pull-ups)
    variants: list[str]                 # e.g., ["pronated", "neutral", "supinated"]
    primary_variant: str                # The standardized test variant
    variant_factors: dict[str, float]   # Normalization factors per variant

    # Session type parameters (S/H/E/T/TEST configs per exercise)
    session_params: dict[str, SessionTypeParams]

    # Progression
    target_metric: str                  # "max_reps" or "1rm_kg"
    target_value: float                 # e.g., 30 reps or 120 kg

    # Assessment
    test_protocol: str                  # Human-readable test instructions
    test_frequency_weeks: int           # Recommended interval between tests

    # 1RM display
    onerm_includes_bodyweight: bool     # True for pull-ups/dips, False for BSS with DBs
    onerm_explanation: str              # User-facing explanation

    # Added weight formula
    weight_increment_fraction: float    # % of relevant load per TM point
    weight_tm_threshold: int            # TM above which weight is added
    max_added_weight_kg: float
```

#### C) History separation

Each exercise gets its own JSONL file:
```text
data/
  pull_up_history.jsonl
  dip_history.jsonl
  bss_history.jsonl
  profile.json
```

The `SessionResult` model must include an `exercise_id` field.

#### D) CLI changes

All commands accept `--exercise` flag (default: `pull_up`):
```bash
bar-scheduler plan --exercise dip
bar-scheduler log-session --exercise bss --date 2026-02-23 --sets "8@20/120,8@20/120,6@20/120"
bar-scheduler plot-max --exercise pull_up
bar-scheduler 1rm --exercise dip
```

**DOC REQUIREMENT**: After implementing the exercise registry, update `README.md` with multi-exercise examples and update `docs/training_model.md` with the `ExerciseDefinition` schema and how `bw_fraction` affects normalization.

---

<a name="exercise-defs"></a>
## 2. Exercise Definitions

### 2.1 Pull-Up (existing, refactored)

```yaml
pull_up:
  display_name: "Pull-Up"
  muscle_group: upper_pull

  # ~100% of bodyweight is lifted during a pull-up.
  # Source: biomechanical analyses of vertical pulling confirm
  # near-total BW displacement minus distal forearm mass (~2-3%).
  bw_fraction: 1.0
  load_type: bw_plus_external

  variants: [pronated, neutral, supinated]
  primary_variant: pronated
  variant_factors:
    pronated: 1.00
    neutral: 1.00
    supinated: 1.00

  target_metric: max_reps
  target_value: 30

  test_frequency_weeks: 3

  onerm_includes_bodyweight: true
  onerm_explanation: >
    Your pull-up 1RM includes your bodyweight. If you weigh 82 kg and can
    do 1 pull-up with +20 kg added, your 1RM is 102 kg.
    Formula: 1RM = (BW + added_weight) × (1 + reps/30) [Epley].

  weight_increment_fraction: 0.01
  weight_tm_threshold: 9
  max_added_weight_kg: 20.0
```

### 2.2 Parallel Bar Dip (new)

```yaml
dip:
  display_name: "Parallel Bar Dip"
  muscle_group: upper_push

  # Approximately 91-92% of bodyweight is lifted during bar dips.
  # The hands+forearms (~5% BW) are not displaced, and upper arms
  # rotate rather than translate, effectively halving their contribution.
  # Source: biomechanical segment analysis; consistent with published
  # approximations of ~91.5% BW for bar dips.
  # A separate source estimates 74-78% for bench dips (different exercise).
  bw_fraction: 0.92
  load_type: bw_plus_external

  variants: [standard, chest_lean, tricep_upright]
  primary_variant: standard
  variant_factors:
    standard: 1.00
    chest_lean: 0.97      # slightly easier due to pec recruitment
    tricep_upright: 1.03   # harder for triceps

  session_params:
    S:
      reps_fraction_low: 0.35
      reps_fraction_high: 0.55
      reps_min: 3
      reps_max: 8
      sets_min: 3
      sets_max: 5
      rest_min: 180
      rest_max: 300
      rir_target: 2
    H:
      reps_fraction_low: 0.55
      reps_fraction_high: 0.75
      reps_min: 6
      reps_max: 15
      sets_min: 4
      sets_max: 6
      rest_min: 120
      rest_max: 180
      rir_target: 2
    E:
      reps_fraction_low: 0.35
      reps_fraction_high: 0.55
      reps_min: 3
      reps_max: 10
      sets_min: 5
      sets_max: 8
      rest_min: 45
      rest_max: 90
      rir_target: 3
    T:
      reps_fraction_low: 0.20
      reps_fraction_high: 0.40
      reps_min: 2
      reps_max: 5
      sets_min: 4
      sets_max: 8
      rest_min: 60
      rest_max: 120
      rir_target: 5
    TEST:
      reps_fraction_low: 1.0
      reps_fraction_high: 1.0
      reps_min: 1
      reps_max: 80
      sets_min: 1
      sets_max: 1
      rest_min: 180
      rest_max: 300
      rir_target: 0

  target_metric: max_reps
  target_value: 40

  test_frequency_weeks: 3

  onerm_includes_bodyweight: true
  onerm_explanation: >
    Your dip 1RM includes your bodyweight. If you weigh 82 kg and can
    do 1 dip with +30 kg, your 1RM is approximately 112 kg × (BW fraction 0.92)
    = 103 kg effective. We display the total load: 112 kg.
    Formula: 1RM = (BW × 0.92 + added_weight) × (1 + reps/30) [Epley].
    Note: the 0.92 factor accounts for the ~8% of BW (hands/forearms) not lifted.

  weight_increment_fraction: 0.012
  weight_tm_threshold: 12
  max_added_weight_kg: 30.0
```

**Source for dip BW fraction**: Biomechanical segment analysis shows hands and forearms (~5% BW) are not displaced and upper arms rotate reducing their effective contribution, resulting in approximately 91.5% of total BW being lifted during bar dips. A kinematic study (McKenzie et al., 2022) confirmed bar dips have greater vertical displacement than bench dips, consistent with near-full BW loading.

### 2.3 Bulgarian Split Squat (BSS) with Dumbbells (new)

```yaml
bss:
  display_name: "Bulgarian Split Squat (DB)"
  muscle_group: lower

  # BSS is a unilateral exercise. The load is external only (dumbbells).
  # Bodyweight contributes to the exercise difficulty but is NOT added
  # to the dumbbell load for 1RM calculation (unlike pull-ups/dips).
  # This matches standard strength-standard conventions for DB exercises.
  # Source: Mackey & Riemann (2021) used 35% of back-squat 1RM for BSS
  # loading in their biomechanical comparison study.
  bw_fraction: 0.0
  load_type: external_only

  variants: [standard, deficit, front_foot_elevated]
  primary_variant: standard
  variant_factors:
    standard: 1.00
    deficit: 1.05           # harder ROM
    front_foot_elevated: 0.95  # slightly easier

  session_params:
    S:
      reps_fraction_low: 0.50
      reps_fraction_high: 0.70
      reps_min: 4
      reps_max: 8
      sets_min: 3
      sets_max: 4
      rest_min: 150
      rest_max: 240
      rir_target: 2
    H:
      reps_fraction_low: 0.60
      reps_fraction_high: 0.80
      reps_min: 8
      reps_max: 15
      sets_min: 3
      sets_max: 5
      rest_min: 90
      rest_max: 150
      rir_target: 2
    E:
      reps_fraction_low: 0.40
      reps_fraction_high: 0.60
      reps_min: 10
      reps_max: 20
      sets_min: 3
      sets_max: 5
      rest_min: 60
      rest_max: 90
      rir_target: 3
    T:
      reps_fraction_low: 0.30
      reps_fraction_high: 0.50
      reps_min: 5
      reps_max: 10
      sets_min: 2
      sets_max: 4
      rest_min: 60
      rest_max: 120
      rir_target: 4
    TEST:
      reps_fraction_low: 1.0
      reps_fraction_high: 1.0
      reps_min: 1
      reps_max: 30
      sets_min: 1
      sets_max: 1
      rest_min: 180
      rest_max: 300
      rir_target: 0

  target_metric: max_reps
  target_value: 20        # 20 reps per leg with 2×24 kg DBs (example)

  test_frequency_weeks: 4

  onerm_includes_bodyweight: false
  onerm_explanation: >
    Your BSS 1RM is the dumbbell weight only (per hand).
    If you hold 2×30 kg dumbbells and do 1 rep, your 1RM is 60 kg (total DB load).
    Bodyweight is NOT included because this is an external-load exercise.
    Formula: 1RM = total_dumbbell_weight × (1 + reps/30) [Epley].

  weight_increment_fraction: 0.0   # Not applicable (load IS the dumbbells)
  weight_tm_threshold: 999         # Never triggers (external load progression instead)
  max_added_weight_kg: 72.0        # 2 × 36 kg max DB
```

**BSS note on sets**: Because BSS is unilateral, each "set" means one set per leg. The planner must prescribe "3 sets" meaning 3 sets on each leg (6 total). The rest interval is between legs (shorter, ~30-60s) and between full rounds (the configured rest). This must be documented in the session plan output.

**Source for BSS biomechanics**: Mackey & Riemann (2021) found BSS is a hip-dominant exercise with significantly less knee joint involvement compared to traditional back squats, making it appropriate for hip-focused strength development. Song et al. (2023) showed step length significantly affects hip/knee activation patterns.

**DOC REQUIREMENT**: After implementing exercise definitions, create `docs/exercises/` folder with one .md per exercise documenting its biomechanics, BW fraction justification, variant differences, and assessment protocol.

---

<a name="1rm-feature"></a>
## 3. 1RM Display Feature

### 3.1 CLI command

```bash
bar-scheduler 1rm --exercise pull_up
```

Output:
```
Pull-Up: Estimated 1RM

  Method: Epley formula — 1RM = W × (1 + R/30)

  Your bodyweight: 82.0 kg
  Best recent weighted set: 5 reps @ +10.0 kg (2026-02-20)
  Total load: 82.0 + 10.0 = 92.0 kg

  Estimated 1RM: 92.0 × (1 + 5/30) = 107.3 kg

  ⚠ This 1RM INCLUDES your bodyweight (82.0 kg).
  Your "added weight 1RM" is approximately 107.3 - 82.0 = 25.3 kg.

  Recent 1RM trend:
  2026-02-01 | ████████████████████ 98.5 kg
  2026-02-10 | █████████████████████ 102.1 kg
  2026-02-20 | ██████████████████████ 107.3 kg
```

For BSS:
```
Bulgarian Split Squat (DB): Estimated 1RM

  Method: Epley formula — 1RM = W × (1 + R/30)

  Best recent set: 8 reps @ 2×24 kg = 48 kg total (2026-02-19)

  Estimated 1RM: 48.0 × (1 + 8/30) = 60.8 kg (total dumbbell load)
  Per hand: ~30.4 kg

  ⚠ This 1RM is dumbbell weight ONLY. Your bodyweight (82 kg) is NOT included.
```

### 3.2 Implementation

```python
def estimate_1rm(
    exercise: ExerciseDefinition,
    bodyweight_kg: float,
    history: list[SessionResult],
    window_sessions: int = 5,
) -> dict:
    """
    Estimate 1RM using Epley formula.

    For BW exercises (bw_fraction > 0):
        total_load = BW × bw_fraction + added_weight
        1RM = total_load × (1 + reps / 30)

    For external-only exercises (bw_fraction == 0):
        total_load = added_weight (or dumbbell weight)
        1RM = total_load × (1 + reps / 30)

    Source: Epley formula, widely validated for 1-10 rep ranges.
    Returns dict with 1rm, method, inputs, and explanation.
    """
```

**DOC REQUIREMENT**: After implementing 1RM, add a section to `docs/training_model.md` explaining:
- Epley formula and its accuracy range (best for 1-10 reps)
- Why BW is included for pull-ups/dips but not for BSS
- How to interpret the number

---

<a name="assessment"></a>
## 4. Assessment Test Protocols

Each exercise needs a brief, standardized test protocol for:
- **Initial assessment** (first use, no history)
- **Periodic re-test** (every N weeks, configurable per exercise)

### 4.1 Pull-Up Test (every 3 weeks)

```
PULL-UP MAX REP TEST

Warm-up:
  1. 2 min arm circles and shoulder dislocates
  2. 1 set of 5 easy pull-ups (or band-assisted if needed)
  3. Rest 2 minutes

Test:
  1. Dead hang, pronated grip (palms forward), shoulder-width
  2. Pull until chin clearly over bar
  3. Lower to full arm extension (dead hang) on each rep
  4. NO kipping, swinging, or leg drive
  5. Continue until you cannot complete a full rep
  6. Count only clean reps

Rest requirement: at least 48 hours since last upper-body training.
Log as: bar-scheduler log-session --exercise pull_up --session-type TEST --sets "N@0/180"
```

### 4.2 Dip Test (every 3 weeks)

```
DIP MAX REP TEST

Warm-up:
  1. 2 min arm swings and light push-ups (10 reps)
  2. 1 set of 5 easy dips (partial ROM if needed)
  3. Rest 2 minutes

Test:
  1. Start position: arms locked out at top, body vertical
  2. Lower until upper arm is at least parallel to floor (~90° elbow)
  3. Press back to full lockout
  4. NO bouncing at bottom, no excessive forward lean
  5. Continue until you cannot complete a full rep with controlled form
  6. Count only clean reps

Rest requirement: at least 48 hours since last upper-push training.
Log as: bar-scheduler log-session --exercise dip --session-type TEST --sets "N@0/180"

Source for technique: McKenzie et al. (2022) profiled bar dip 
kinematics — greater vertical displacement and triceps/pec activation 
compared to bench dips.
```

### 4.3 Bulgarian Split Squat Test (every 4 weeks)

```
BULGARIAN SPLIT SQUAT MAX REP TEST (per leg)

Setup:
  - Bench height: approximately knee height (~45-50 cm)
  - Hold one dumbbell in each hand (choose a weight you can do 5-15 reps with)
  - Rear foot on bench, laces down
  - Front foot ~60-75 cm in front of bench

Warm-up:
  1. 2 min bodyweight lunges (5 per leg)
  2. 1 set of 5 BSS per leg with light weight (50% test weight)
  3. Rest 2 minutes

Test:
  1. Start standing, rear foot on bench
  2. Lower until front thigh is at or below parallel
  3. Drive back up to full extension
  4. Maintain upright torso (slight forward lean acceptable)
  5. Continue until you cannot complete a clean rep
  6. Rest 2-3 minutes, then test other leg
  7. Record the LOWER of the two legs as your score

Rest requirement: at least 48 hours since last lower-body training.
Log as: bar-scheduler log-session --exercise bss --session-type TEST --sets "N@48/180" 
  (where 48 = total dumbbell weight in kg, N = reps of weaker leg)

Note: BSS 1RM estimation uses Epley on the dumbbell weight only, not bodyweight.

Source for BSS standards: Mackey & Riemann (2021) studied BSS mechanics; 
Song et al. (2023) showed step length affects muscle activation patterns. 
Both confirm BSS as a hip-dominant exercise.
```

### 4.4 Periodic re-testing schedule

The planner must automatically insert a TEST session into the plan:
- Pull-ups: every 3 weeks (21 days ± 2)
- Dips: every 3 weeks (21 days ± 2)
- BSS: every 4 weeks (28 days ± 3)

These are configurable per exercise in `exercises.yaml` via `test_frequency_weeks`.

When a TEST session is upcoming, the plan should:
1. Schedule a lighter session the day before (or rest day).
2. Place TEST at the start of a training day (first exercise after warm-up).
3. After TEST, allow a normal training session of a different type if the user wants.

**DOC REQUIREMENT**: After implementing test protocols, create `docs/assessment_protocols.md` with all test descriptions and add test schedule info to `docs/training_model.md`.

---

<a name="fixes"></a>
## 5. Consolidated Fix List (all issues, priority order)

### CRITICAL

| # | Title | File(s) | Summary |
|---|-------|---------|---------|
| 11 | Plan instability: schedule reset, week reset, retroactive changes | planner.py | Past prescriptions overwritten; schedule always restarts from S; week counter resets to 1. Fix: immutable history, resume rotation from last session, cumulative weeks. |
| 2 | Weekly progression applied per session | planner.py | Progression multiplied by sessions/week. Fix: apply once per week boundary. |
| 6 | Rest normalization double-counts | metrics.py, physiology.py | Short rest increases both normalized reps AND training load. Fix: ensure two paths are independent. |

### HIGH

| # | Title | File(s) | Summary |
|---|-------|---------|---------|
| 12 | Added weight ignores bodyweight | planner.py, config.yaml | Fixed formula: `BW × 0.01 × (TM - threshold)`. |
| 13 | Rest prescription is static midpoint | planner.py | Implement adaptive rest based on last session's RIR and drop-off. |
| 1 | TM bypasses TM_FACTOR | planner.py | Use `status.training_max`, not raw test max. |
| 19 | Multi-exercise architecture extraction | all core/ | Extract ExerciseDefinition, parameterize engine, separate histories. |
| 20 | 1RM display feature | new cli command, metrics.py | Epley-based 1RM with BW-inclusion explanation per exercise type. |
| 21 | Assessment test protocols | planner.py, exercises.yaml | Auto-schedule TEST sessions per exercise at configured intervals. |

### MEDIUM

| # | Title | File(s) | Summary |
|---|-------|---------|---------|
| 15 | Contradictory TM in explanation | planner.py | Fix after #1: show only correct TM value. |
| 14 | Constants to YAML | config.py → config.yaml | All model constants in commented YAML. |
| 9 | Session params deviate from spec | config.yaml | Revert to documented defaults. |
| 3 | Day spacing irregular | planner.py | Use fixed weekday patterns. |
| 5 | Autoregulation gate too low | planner.py, config.yaml | Increase to 10 sessions minimum. |
| 22 | BSS unilateral set display | views.py | Show "3 sets per leg" not just "3 sets". |

### LOW

| # | Title | File(s) | Summary |
|---|-------|---------|---------|
| 10 | Initial readiness_var too low | physiology.py | Set to 10.0 at init. |
| 16 | Intra-week fractional progression | planner.py | Remove; apply TM once per week. |
| 8 | Remove TM cap at target | planner.py | Let TM grow past target_max_reps. |
| 7 | Grip rotation mutation silent | planner.py | Add docstring. |
| 17 | Endurance volume multiplier | planner.py | kE grows from 3.0 to 5.0 with TM. |
| 18 | SessionPlan unreachable validation | models.py | Move validation before property. |

**DOC REQUIREMENT**: After completing all CRITICAL and HIGH fixes, do a full pass on `README.md` and `docs/training_model.md` to ensure they match the new behavior. Add a CHANGELOG.md entry.

---

<a name="per-user"></a>
## 6. Per-User Settings (`data/profile.json`)

```json
{
  "height_cm": 175,
  "sex": "male",
  "current_bodyweight_kg": 82.0,
  "preferred_days_per_week": 4,
  "preferred_training_days": ["mon", "wed", "fri", "sat"],
  "available_equipment": {
    "horizontal_bar": true,
    "parallel_grip_bar": true,
    "dip_bars": true,
    "low_bar": true,
    "bench": true,
    "dumbbells_max_kg": 36,
    "weight_belt": true
  },
  "exercises_enabled": ["pull_up", "dip", "bss"],
  "max_session_duration_minutes": 60,
  "rest_preference": "normal",
  "injury_notes": ""
}
```

---

<a name="adaptation"></a>
## 7. User Guide: Adaptation Timelines

This text must be displayed on `bar-scheduler help adaptation` and included in README.

```
HOW THE PLANNER LEARNS FROM YOUR DATA

This planner is adaptive. Here is what it knows at each stage:

┌─────────────────┬──────────────────────────────────────────────────────┐
│ Stage           │ What the model can do                                │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Day 1           │ Generic safe plan from your baseline max.            │
│ (no history)    │ Conservative volume. No weighted work until TM > 9.  │
│                 │ RECOMMENDATION: Just follow the plan and log.        │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 1–2       │ EWMA max estimate starts tracking.                   │
│ (3–8 sessions)  │ Rest normalization active (short rest gets credit).  │
│                 │ NO autoregulation yet (not enough data).             │
│                 │ RECOMMENDATION: Log rest times accurately.           │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 3–4       │ AUTOREGULATION ACTIVATES (≥10 sessions).             │
│ (10–16 sessions)│ Plateau detection possible.                          │
│                 │ Rest adaptation kicks in (RIR + drop-off based).     │
│                 │ RECOMMENDATION: Do your first re-test (TEST session).│
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 6–8       │ Individual fatigue profile fitted.                   │
│ (24–32 sessions)│ Set-to-set predictions improve.                      │
│                 │ Deload triggers become reliable.                     │
│                 │ RECOMMENDATION: Trust the deload if recommended.     │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 12+       │ Full training profile established.                   │
│ (48+ sessions)  │ Long-term fitness adaptation curve accurate.         │
│                 │ Progression rate calibrated to your response.        │
│                 │ RECOMMENDATION: Model is at peak accuracy.           │
└─────────────────┴──────────────────────────────────────────────────────┘

TIPS FOR BEST RESULTS:
• Log every session, including bad ones (RIR=0, incomplete sets = valuable data)
• Log rest times, even approximate
• Do a TEST session every 3–4 weeks (anchors the max estimate)
• Update bodyweight when it changes by ≥1 kg
• Past prescriptions are frozen — only future sessions adapt
• Different exercises have separate plans and separate adaptation timelines
```

---

<a name="docs"></a>
## 8. Documentation Requirements (mandatory after each feature)

After every significant feature implementation, the engineer MUST update:

| Feature completed | Files to update |
|-------------------|----------------|
| Exercise registry + ExerciseDefinition | `README.md` (add multi-exercise section), `docs/training_model.md` (add ExerciseDefinition schema, bw_fraction explanation) |
| Pull-up exercise config | `docs/exercises/pull_up.md` (create) |
| Dip exercise config | `docs/exercises/dip.md` (create, include McKenzie 2022 biomechanics reference) |
| BSS exercise config | `docs/exercises/bss.md` (create, include Mackey 2021 and Song 2023 references) |
| 1RM display | `docs/training_model.md` (add 1RM section with Epley explanation and BW-inclusion rules), `README.md` (add 1RM command example) |
| Assessment protocols | `docs/assessment_protocols.md` (create), `README.md` (add test schedule info) |
| YAML config migration | `docs/training_model.md` (update all constant references to YAML paths), `README.md` (add config customization section) |
| Adaptive rest | `docs/training_model.md` (add adaptive rest formula section) |
| Plan stability fixes (#11) | `docs/training_model.md` (add "plan regeneration" section explaining immutable history), `README.md` (add FAQ on plan changes) |
| Per-user settings | `README.md` (add profile configuration section) |
| Adaptation timeline guide | `README.md` (embed or link to adaptation guide), create `docs/adaptation_guide.md` |

---

## References (for engineer, to cite in docs/)

1. McKenzie A, et al. (2022). Bench, Bar, and Ring Dips: Kinematics and Muscle Activity. PMCID: PMC9603242.
2. Mackey ER, Riemann BL (2021). Biomechanical Differences Between the Bulgarian Split-Squat and Back Squat. Int J Exerc Sci, 14(1):533-543.
3. Song Q, et al. (2023). Effects of step lengths on biomechanical characteristics in split squat. Front Bioeng Biotechnol, 11:1277493.
4. Aygun-Polat E, et al. (2025). Targeted muscle activation in Bulgarian split squat variations. PMCID: PMC12382192.
5. McKenzie A, et al. (2022). Fatigue Increases Muscle Activations but Does Not Change Maximal Joint Angles in Bar Dips. PMCID: PMC9659300.
6. Epley formula: 1RM = W × (1 + R/30). Validated for 1-10 rep ranges across barbell and bodyweight exercises.
7. Dip BW fraction (~91.5%): biomechanical segment analysis (hands/forearms not displaced, upper arm rotation effect).
8. 1RM test frequency: every 4-6 weeks is standard practice in periodized programs, with 3-4 week cycles common for intermediate trainees.

---
