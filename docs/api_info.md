# bar-scheduler Python Library API

bar-scheduler is a Python package. External consumers — Telegram bots, web apps, scripts — import it directly and call functions; no CLI is required. All persistent data lives in `~/.bar-scheduler/` (`profile.json` for profile and equipment, `{exercise_id}_history.jsonl` for each exercise's sessions).

## Import cheat sheet

```python
from bar_scheduler.io.history_store import (
    HistoryStore, get_profile_store, get_default_history_path, get_data_dir,
)
from bar_scheduler.core.models import (
    UserProfile, ExerciseTarget, UserState,
    SetResult, PlannedSet, SessionResult, SessionPlan,
    EquipmentState, EquipmentSnapshot,
    TrainingStatus, FitnessFatigueState,
)
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.adaptation import get_training_status
from bar_scheduler.core.planner import generate_plan, explain_plan_entry
from bar_scheduler.core.metrics import (
    session_total_reps, session_max_reps, session_avg_rest,
    get_test_sessions, latest_test_max, estimate_1rm,
)
from bar_scheduler.core.equipment import (
    get_catalog, compute_leff, snapshot_from_state,
)
from bar_scheduler.io.serializers import parse_sets_string, ValidationError
```

---

## Key data models

### `UserProfile`

```python
@dataclass
class UserProfile:
    height_cm: int
    sex: Literal["male", "female"]
    preferred_days_per_week: int = 3        # 1–5, fallback for exercises not in exercise_days
    exercise_days: dict = {}                # {"pull_up": 3, "dip": 4}
    exercise_targets: dict = {}             # {"pull_up": ExerciseTarget(30)}
    exercises_enabled: list = []            # ["pull_up", "dip"]
    max_session_duration_minutes: int = 60
    rest_preference: str = "normal"         # "short" | "normal" | "long"
    injury_notes: str = ""
    language: str = "en"                    # ISO 639-1; controls t() output
```

Methods: `days_for_exercise(exercise_id)`, `target_for_exercise(exercise_id)`, `is_exercise_enabled(exercise_id)`.

### `ExerciseTarget`

```python
@dataclass
class ExerciseTarget:
    reps: int           # target rep count (must be > 0)
    weight_kg: float = 0.0  # added weight (0 = bodyweight goal)
```

### `UserState`

```python
@dataclass
class UserState:
    profile: UserProfile
    current_bodyweight_kg: float
    history: list[SessionResult] = []
```

### `SetResult` / `PlannedSet`

```python
@dataclass
class SetResult:
    target_reps: int
    actual_reps: int | None     # None = not yet completed
    rest_seconds_before: int
    added_weight_kg: float = 0.0
    rir_target: int = 2
    rir_reported: int | None = None

@dataclass
class PlannedSet:                # future sets — no actual_reps
    target_reps: int
    rest_seconds_before: int
    added_weight_kg: float = 0.0
    rir_target: int = 2
```

### `SessionResult`

```python
@dataclass
class SessionResult:
    date: str                               # "YYYY-MM-DD"
    bodyweight_kg: float
    grip: str                               # exercise-specific variant, e.g. "pronated"
    session_type: Literal["S","H","E","T","TEST"]
    exercise_id: str                        # "pull_up" | "dip" | "bss"
    equipment_snapshot: EquipmentSnapshot | None = None
    planned_sets: list[SetResult] = []
    completed_sets: list[SetResult] = []
    notes: str | None = None
```

Session types: `S` = Strength, `H` = Hypertrophy, `E` = Endurance, `T` = Technique, `TEST` = max assessment (max reps for bodyweight exercises, 1RM for weighted exercises).

### `SessionPlan`

```python
@dataclass
class SessionPlan:
    date: str
    grip: str
    session_type: str
    exercise_id: str
    sets: list[PlannedSet] = []
    expected_tm: int = 0    # projected training max at this point in the plan
    week_number: int = 1    # 1-indexed calendar week
```

Property: `total_reps` — sum of `target_reps` across all sets.
Method: `to_session_result(bodyweight_kg)` → `SessionResult` shell ready for logging.

### `TrainingStatus`

```python
@dataclass
class TrainingStatus:
    training_max: int               # floor(0.9 × latest_test_max)
    latest_test_max: int | None
    trend_slope: float              # reps/week (linear regression)
    is_plateau: bool
    deload_recommended: bool
    compliance_ratio: float         # actual / planned reps ratio
    fatigue_score: float
    fitness_fatigue_state: FitnessFatigueState
```

`FitnessFatigueState` methods: `readiness()` → `G(t)−H(t)`, `readiness_z_score()` → autoregulation signal.

---

## 1. Profile: check & create

```python
from bar_scheduler.io.history_store import get_profile_store
from bar_scheduler.core.models import UserProfile, ExerciseTarget

store = get_profile_store()

# Check if profile exists
profile = store.load_profile()
bodyweight = store.load_bodyweight()
profile_exists = profile is not None and bodyweight is not None

# Create / overwrite profile
profile = UserProfile(
    height_cm=180,
    sex="male",
    preferred_days_per_week=3,
    exercises_enabled=["pull_up"],
    language="en",
)
store.save_profile(profile, bodyweight_kg=82.0)
```

`save_profile(profile, bodyweight_kg)` writes both the profile and current bodyweight atomically to `profile.json`. It creates the data directory if needed.

---

## 2. Profile: edit

```python
store = get_profile_store()
profile = store.load_profile()
bw = store.load_bodyweight()

# Change bodyweight only (cheap, no profile reload needed)
store.update_bodyweight(85.0)

# Change display language
store.update_language("ru")   # "en" | "ru" | "zh"

# Structural changes (days, rest preference, etc.) — mutate and re-save
profile.preferred_days_per_week = 4
profile.rest_preference = "long"
store.save_profile(profile, bw)
```

---

## 3. Exercises: add & remove

Built-in exercise IDs: `"pull_up"`, `"dip"`, `"bss"`. Validate with `get_exercise(id)` — raises `ValueError` for unknown IDs.

### Add an exercise

```python
from bar_scheduler.io.history_store import HistoryStore, get_default_history_path, get_profile_store
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.planner import create_synthetic_test_session
from datetime import date

exercise_id = "dip"
exercise = get_exercise(exercise_id)   # validates ID

# 1. Create per-exercise history file
history_path = get_default_history_path(exercise_id)
ex_store = HistoryStore(history_path, exercise_id=exercise_id)
ex_store.init()                        # creates ~/.bar-scheduler/dip_history.jsonl

# 2. Set plan anchor
ex_store.set_plan_start_date(date.today().isoformat())

# 3. Log a baseline TEST session so the planner has a starting TM
baseline_max = 15
session = create_synthetic_test_session(
    date=date.today().isoformat(),
    bodyweight_kg=82.0,
    baseline_max=baseline_max,
    exercise_id=exercise_id,
)
ex_store.append_session(session)

# 4. Mark exercise as enabled in profile
profile_store = get_profile_store()
profile = profile_store.load_profile()
bw = profile_store.load_bodyweight()
if exercise_id not in profile.exercises_enabled:
    profile.exercises_enabled.append(exercise_id)
profile_store.save_profile(profile, bw)
```

### Remove an exercise

Removing means disabling it in the profile. The history file can be left on disk or deleted manually — the library never auto-deletes it.

```python
profile_store = get_profile_store()
profile = profile_store.load_profile()
bw = profile_store.load_bodyweight()

profile.exercises_enabled = [e for e in profile.exercises_enabled if e != "dip"]
profile.exercise_days.pop("dip", None)
profile.exercise_targets.pop("dip", None)
profile_store.save_profile(profile, bw)
```

---

## 4. Goals: add & update

Goals are `ExerciseTarget` values stored in `profile.exercise_targets`. They drive `estimate_plan_completion_date()` and the trajectory overlays in plot data.

```python
from bar_scheduler.core.models import ExerciseTarget

profile_store = get_profile_store()
profile = profile_store.load_profile()
bw = profile_store.load_bodyweight()

# Set or update goal for pull_up: 25 bodyweight reps
profile.exercise_targets["pull_up"] = ExerciseTarget(reps=25)

# Weighted goal: 15 dips with +20 kg
profile.exercise_targets["dip"] = ExerciseTarget(reps=15, weight_kg=20.0)

profile_store.save_profile(profile, bw)

# Read back
target = profile.target_for_exercise("pull_up")
# target.reps == 25, target.weight_kg == 0.0
```

---

## 5. Equipment: add & update

Equipment is stored per-exercise in `profile.json` as an append-only history. Each change closes the previous entry and starts a new one.

### Available equipment items

```python
from bar_scheduler.core.equipment import get_catalog

catalog = get_catalog("pull_up")
# Keys: "BAR_ONLY", "BAND_LIGHT", "BAND_MEDIUM", "BAND_HEAVY",
#       "MACHINE_ASSISTED", "WEIGHT_BELT"

catalog = get_catalog("dip")
# Similar: "BAR_ONLY", "BAND_LIGHT", etc., "WEIGHT_BELT"

catalog = get_catalog("bss")
# Keys: "BODYWEIGHT", "DUMBBELLS", "BARBELL",
#       "RESISTANCE_BAND", "ELEVATION_SURFACE"
```

Each catalog entry has `"assistance_kg"` (positive = assistive, 0 = neutral/additive).

### Read current equipment

```python
from bar_scheduler.io.history_store import get_default_history_path, HistoryStore

store = HistoryStore(get_default_history_path("pull_up"), exercise_id="pull_up")
eq_state = store.load_current_equipment("pull_up")   # EquipmentState | None
if eq_state:
    print(eq_state.active_item)         # e.g. "BAR_ONLY"
    print(eq_state.available_items)     # e.g. ["BAR_ONLY", "WEIGHT_BELT"]
    print(eq_state.assistance_kg if hasattr(eq_state, 'assistance_kg') else 0)
```

### Set / update equipment

```python
from bar_scheduler.core.models import EquipmentState
from datetime import date

new_state = EquipmentState(
    exercise_id="pull_up",
    available_items=["BAR_ONLY", "BAND_MEDIUM", "WEIGHT_BELT"],
    active_item="BAND_MEDIUM",          # currently using medium band (assistive)
    machine_assistance_kg=None,
    elevation_height_cm=None,
    valid_from=date.today().isoformat(),
)
store.update_equipment(new_state)
# closes previous entry (valid_until = yesterday), appends new one
```

For `MACHINE_ASSISTED` items set `machine_assistance_kg` to the machine's assistance value in kg. For BSS `ELEVATION_SURFACE` set `elevation_height_cm` to 30, 45, or 60.

### Effective load calculation

```python
from bar_scheduler.core.equipment import compute_leff, get_catalog

catalog = get_catalog("pull_up")
assistance_kg = catalog["BAND_MEDIUM"]["assistance_kg"]   # e.g. 15.0

leff = compute_leff(
    bw_fraction=1.0,        # from ExerciseDefinition
    bodyweight_kg=82.0,
    added_weight_kg=0.0,
    assistance_kg=assistance_kg,
)
# leff = 82.0 - 15.0 = 67.0 kg
```

---

## 6. History: read

```python
from bar_scheduler.io.history_store import HistoryStore, get_default_history_path
from bar_scheduler.core.metrics import (
    session_total_reps, session_max_reps, session_avg_rest,
    get_test_sessions, latest_test_max,
)

store = HistoryStore(get_default_history_path("pull_up"), exercise_id="pull_up")
history = store.load_history()   # list[SessionResult], sorted by date

# Per-session metrics
for s in history:
    print(s.date, s.session_type, s.grip)
    print("  total reps:", session_total_reps(s))
    print("  best set:  ", session_max_reps(s))
    print("  avg rest:  ", session_avg_rest(s), "s")

# TEST sessions only
tests = get_test_sessions(history)
tm = latest_test_max(history)   # int | None
```

### `SessionResult` key fields

| Field | Type | Notes |
|---|---|---|
| `date` | `str` | `"YYYY-MM-DD"` |
| `session_type` | `str` | `S`, `H`, `E`, `T`, `TEST` |
| `grip` | `str` | exercise-specific variant |
| `exercise_id` | `str` | `"pull_up"`, `"dip"`, `"bss"` |
| `bodyweight_kg` | `float` | logged bodyweight |
| `completed_sets` | `list[SetResult]` | actual sets performed |
| `planned_sets` | `list[SetResult]` | prescribed sets (from plan cache) |
| `equipment_snapshot` | `EquipmentSnapshot \| None` | equipment at log time |
| `notes` | `str \| None` | free text |

### Filtering and slicing

```python
# All sessions for one exercise after a date
from datetime import date
cutoff = "2026-01-01"
recent = [s for s in history if s.date >= cutoff]

# Load full user state (profile + bodyweight + history in one call)
user_state = store.load_user_state()   # UserState
```

---

## 7. History: write & delete

### Log a session

```python
from bar_scheduler.core.models import SessionResult, SetResult

session = SessionResult(
    date="2026-03-22",
    bodyweight_kg=82.0,
    grip="pronated",
    session_type="S",
    exercise_id="pull_up",
    completed_sets=[
        SetResult(target_reps=5, actual_reps=5, rest_seconds_before=180, added_weight_kg=0.0, rir_reported=2),
        SetResult(target_reps=5, actual_reps=4, rest_seconds_before=180, added_weight_kg=0.0, rir_reported=1),
        SetResult(target_reps=5, actual_reps=4, rest_seconds_before=180, added_weight_kg=0.0, rir_reported=1),
    ],
)
store.append_session(session)
# inserts in chronological order; same (date, session_type) replaces the existing entry
```

### Parse a sets string (helper)

```python
from bar_scheduler.io.serializers import parse_sets_string

# Returns list of (reps, added_weight_kg, rest_seconds)
sets = parse_sets_string("4x5 +0.5kg / 240s")
# → [(5, 0.5, 240), (5, 0.5, 240), (5, 0.5, 240), (5, 0.5, 240)]

sets = parse_sets_string("8@0/180, 6@5/180")
# → [(8, 0.0, 180), (6, 5.0, 180)]

sets = parse_sets_string("8 0 180")   # space-separated
# → [(8, 0.0, 180)]
```

Raises `ValidationError` on invalid input.

### Update bodyweight after logging

```python
store.update_bodyweight(82.5)
```

### Delete a session

```python
history = store.load_history()   # sorted list, 0-based index

# delete the third session (0-based)
store.delete_session_at(2)

# if you got the ID from a TimelineEntry (actual_id is 1-based):
store.delete_session_at(entry.actual_id - 1)
```

---

## 8. Training plan

### Training status

```python
from bar_scheduler.core.adaptation import get_training_status

user_state = store.load_user_state()
status = get_training_status(
    history=user_state.history,
    current_bodyweight_kg=user_state.current_bodyweight_kg,
    baseline_max=None,   # provide only if history is empty
)

status.training_max           # int — floor(0.9 × latest_test_max)
status.latest_test_max        # int | None
status.trend_slope            # float — reps/week
status.is_plateau             # bool
status.deload_recommended     # bool
status.compliance_ratio       # float — actual/planned reps ratio
status.fitness_fatigue_state.readiness_z_score()   # float — autoregulation signal
```

### Generate a plan

```python
from bar_scheduler.core.planner import generate_plan
from bar_scheduler.core.exercises.registry import get_exercise

exercise = get_exercise("pull_up")   # ExerciseDefinition
plan_start = store.get_plan_start_date() or "2026-03-22"

plans = generate_plan(
    user_state=user_state,
    start_date=plan_start,
    exercise=exercise,
    weeks_ahead=4,          # None = auto-estimate based on distance to goal
    baseline_max=None,      # required only if no TEST session in history
)
# returns list[SessionPlan], one entry per scheduled training day

for session_plan in plans:
    print(session_plan.date, session_plan.session_type, session_plan.grip)
    print("  week:", session_plan.week_number)
    print("  expected TM:", session_plan.expected_tm)
    for s in session_plan.sets:
        print(f"  {s.target_reps} reps @ {s.added_weight_kg} kg / {s.rest_seconds_before}s rest")
```

`generate_plan` raises `ValueError` when there is no history and `baseline_max` is `None`.

### Unified timeline (past + future)

`build_timeline` is a convenience function in the CLI layer that merges history and plan into a single chronological list. Useful if you want to display a combined view.

```python
from bar_scheduler.cli.views import build_timeline, TimelineEntry

entries = build_timeline(plans, user_state.history)

for entry in entries:
    print(entry.date, entry.status)  # "done" | "missed" | "next" | "planned" | "extra" | "rested"
    if entry.planned:
        print("  prescribed:", entry.planned.sets)
    if entry.actual:
        print("  actual:", entry.actual.completed_sets)
    if entry.track_b:
        # Between-test max estimates (FI method + Nuzzo method)
        print("  eMax estimate:", entry.track_b["fi_est"], "/", entry.track_b["nuzzo_est"])
```

`TimelineEntry.actual_id` is the 1-based history index for use with `delete_session_at(actual_id - 1)`.

### Plan start date management

```python
store.get_plan_start_date()         # str | None — current plan anchor for this exercise
store.set_plan_start_date("2026-03-22")   # move plan anchor (e.g. after a break)
```

---

## 9. Explanation text

```python
from bar_scheduler.core.planner import explain_plan_entry

text = explain_plan_entry(
    user_state=user_state,
    plan_start_date=plan_start,
    target_date="2026-03-24",       # or use "next" logic: first session with status "next"
    exercise=exercise,
    weeks_ahead=4,
)
# Returns a Rich markup string.

# To display in a Rich console:
from rich.console import Console
Console().print(text)

# To get plain text (e.g. for Telegram):
from rich.text import Text
plain = Text.from_markup(text).plain
```

The function has three fallback levels:
1. Session is in the plan → full breakdown (TM formula, grip rotation, set config, weight, rest)
2. Date is within the plan horizon but not a training day → rest day message
3. Date is in history (past) → brief session summary

---

## 10. Data for plotting

bar-scheduler does not generate graphics. It returns structured data that the consumer renders. Below are the data sources for the most common chart types.

### Progress chart (max reps over time)

```python
from bar_scheduler.core.metrics import get_test_sessions

tests = get_test_sessions(user_state.history)
# Each SessionResult — use .date and session_max_reps(s)

data_points = [
    {"date": s.date, "max_reps": session_max_reps(s)}
    for s in tests
]
# [{"date": "2026-02-01", "max_reps": 10}, ...]
```

### Training max trajectory (goal projection)

```python
from bar_scheduler.core.config import expected_reps_per_week
from bar_scheduler.core.metrics import training_max as compute_tm
from datetime import date, timedelta

tm = compute_tm(user_state.history)      # current TM
target = exercise.target_value           # goal (from ExerciseDefinition)

trajectory = []
current = date.today()
current_tm = float(tm)
for week in range(16):
    trajectory.append({"date": current.isoformat(), "projected_max_reps": int(current_tm / 0.9)})
    current_tm += expected_reps_per_week(int(current_tm), int(target))
    current += timedelta(weeks=1)
```

### Weekly volume

```python
from datetime import date

def week_label(iso_date: str) -> str:
    """Return ISO year-week string for grouping, e.g. '2026-W12'."""
    d = date.fromisoformat(iso_date)
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"

from collections import defaultdict
from bar_scheduler.core.metrics import session_total_reps

volume: dict[str, int] = defaultdict(int)
for s in user_state.history:
    volume[week_label(s.date)] += session_total_reps(s)

# [{"week": "2026-W10", "total_reps": 85}, ...]
weekly = [{"week": wk, "total_reps": reps} for wk, reps in sorted(volume.items())]
```

### 1RM estimate

```python
from bar_scheduler.core.metrics import estimate_1rm

result = estimate_1rm(
    exercise=exercise,
    bodyweight_kg=user_state.current_bodyweight_kg,
    history=user_state.history,
    window_sessions=5,
)

if result:
    result["1rm_kg"]                 # float — best estimate
    result["best_reps"]              # int
    result["best_added_weight_kg"]   # float
    result["best_date"]              # str "YYYY-MM-DD"
    result["formulas"]               # dict: epley, brzycki, lander, lombardi, blended
    result["recommended_formula"]    # str — most accurate for this rep count
```

Returns `None` if no eligible sets are found within the scan window.

### Fitness-fatigue state (readiness over time)

```python
status = get_training_status(user_state.history, user_state.current_bodyweight_kg)
ff = status.fitness_fatigue_state

ff.fitness          # float — G(t), slow-decay fitness impulse
ff.fatigue          # float — H(t), fast-decay fatigue impulse
ff.readiness()      # float — G(t) − H(t)
ff.readiness_z_score()  # float — z-score for autoregulation
```

To build a readiness time series, call `get_training_status` with a slice of history up to each date. For most bot use cases the current scalar values above are sufficient.

---

## Storage layout

```
~/.bar-scheduler/
  profile.json                    — UserProfile + bodyweight + equipment history + plan anchors
  pull_up_history.jsonl           — pull-up sessions (one JSON line per session)
  dip_history.jsonl               — dip sessions
  bss_history.jsonl               — BSS sessions
  plan_cache.json                 — last generated plan snapshot (for change diffing)
```

```python
from bar_scheduler.io.history_store import get_data_dir, get_default_history_path

get_data_dir()                          # Path("~/.bar-scheduler")
get_default_history_path("pull_up")     # Path("~/.bar-scheduler/pull_up_history.jsonl")
```
