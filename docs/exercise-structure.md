# Exercise Structure Reference

How bar-scheduler exercises are defined, how the loader works, and how to add a
custom exercise or override existing values.

---

## Where exercise definitions live

```
src/bar_scheduler/exercises/         ← bundled per-exercise YAML (one file each)
  pull_up.yaml  dip.yaml  bss.yaml  incline_db_press.yaml
~/.bar-scheduler/exercises/          ← optional user overrides (one file per id)
src/bar_scheduler/core/exercises/
  base.py        ← ExerciseDefinition + SessionTypeParams (also the OmegaConf schema)
  repository.py  ← ExerciseRepository: lazy, per-id load + deep-merge (OmegaConf)
  registry.py    ← get_exercise(id), list_exercise_ids(), all_exercises()
```

One exercise is loaded **on demand** from `<id>.yaml`. `ExerciseRepository`
reads the bundled file, then deep-merges the user file (if present) over it via
OmegaConf, coercing values against the `ExerciseDefinition` structured schema.
`list_exercise_ids()` cheaply enumerates `*.yaml` stems without parsing every
file. There is no per-exercise Python-constant fallback — the YAML is the source
of truth.

> Note: the separate `src/bar_scheduler/exercises.yaml` (no subdirectory) holds
> the **model constants** (`config/loader.py`), not exercise definitions. See
> [model.md §14](model.md#14-config-constants-config).

---

## ExerciseDefinition schema

Each `<id>.yaml` defines one exercise with these fields (top level, no wrapper).

| Field | Type | Description |
|-------|------|-------------|
| `exercise_id` | `str` | Unique snake_case key (must match the filename) |
| `display_name` | `str` | Human-readable label |
| `muscle_group` | `str` | Informational tag (e.g. `upper_pull`) |
| `bw_fraction` | `float` | Fraction of bodyweight that is working load (1.0 = pull-up, 0.0 = external-only) |
| `load_type` | `str` | `bw_plus_external` or `external_only` |
| `variants` | `list[str]` | All valid movement variants |
| `primary_variant` | `str` | Used for standardised testing (must be in `variants`) |
| `variant_factors` | `dict[str, float]` | Relative difficulty per variant (1.0 = neutral) |
| `session_params` | `dict[str, SessionTypeParams]` | Per session type (see below) |
| `target_metric` | `str` | `max_reps` or `1rm_kg` |
| `target_value` | `float` | Long-term goal (e.g. `30` reps) |
| `test_protocol` | `str` | Human-readable test instructions (YAML literal block `\|`) |
| `test_frequency_weeks` | `int` | Weeks between auto-inserted TEST sessions |
| `onerm_includes_bodyweight` | `bool` | Whether the 1RM display adds BW to effective load |
| `onerm_explanation` | `str` | Shown by the 1RM endpoint |
| `weight_increment_fraction` | `float` | Fraction of effective load per TM point above threshold |
| `weight_tm_threshold` | `int` | TM must exceed this before added weight is prescribed |
| `max_added_weight_kg` | `float` | Hard cap on prescribed added weight |
| `level_thresholds` | `list[int]?` | Strictly-ascending test-max cutpoints; N thresholds → N+1 levels |
| `set_fatigue_curve` | `list[float]` | Per-set rep-decay multipliers (set 1 = 1.0); last value reused past its length |
| `equipment` | `dict[str, dict]` | Catalog: `item_id → {label, assistance_kg, requires_weight_declaration}` |
| `default_item` | `str` | Equipment item pre-selected when the exercise is first added |
| `dual_dumbbell` | `bool` | Two-dumbbell exercise — planner expands single + pair weight totals |

### Optional field defaults

| Field | Default |
|-------|---------|
| `has_variant_rotation` | `true` |
| `grip_cycles` | `{}` (no rotation) |
| `level_thresholds` | `None` (level-based set counts disabled → midpoint set count) |
| `set_fatigue_curve` | `[1.0]` (no intra-session decay) |
| `equipment` / `default_item` / `dual_dumbbell` | `{}` / `""` / `false` |

---

## SessionTypeParams sub-schema

Each key under `session_params` maps a session type (`S`, `H`, `E`, `T`, `TEST`)
to:

| Field | Type | Required? | Description |
|-------|------|-----------|-------------|
| `reps_fraction_low` / `reps_fraction_high` | `float` | yes | Rep target as a fraction of TM |
| `reps_min` / `reps_max` | `int` | yes | Absolute rep floor / ceiling per set |
| `rest_min` / `rest_max` | `int` | yes | Rest between sets (seconds) |
| `rir_target` | `int` | yes | Reps-in-reserve target |
| `sets_min` / `sets_max` | `int` | no (default 1 / 10) | Set-count bounds (midpoint used when levels undefined) |
| `sets_by_level` | `list[int]?` | no | Set count per level index (0 = lowest); pairs with `level_thresholds` |

---

## grip_cycles rules

`grip_cycles` maps a session-type string to an ordered variant list; the planner
keeps a per-type counter and picks position `count % len(cycle)`:

```yaml
grip_cycles:
  S: [pronated, neutral, supinated]   # cycles every 3 S sessions
  H: [pronated, neutral, supinated]
  T: [pronated, neutral]
  E: [pronated]
  TEST: [pronated]
```

When `has_variant_rotation: false`, `grip_cycles` is ignored and
`primary_variant` is always used; omit it or set `{}`.

---

## Validator behaviour (`repository.py`)

- **Unknown exercise id** (no bundled or user file) → `ValueError("Unknown exercise …")`.
- **`level_thresholds` not strictly ascending** → `ValueError(… "ascending" …)`.
- **Type coercion & required fields** are enforced by the OmegaConf structured
  schema (`ExerciseDefinition`); a malformed value raises at load time.
- User files **deep-merge** over the bundled file per id, so a user override need
  only list the keys it changes.

---

## User override: `~/.bar-scheduler/exercises/<id>.yaml`

Override any field without touching source. Create
`~/.bar-scheduler/exercises/pull_up.yaml` with only the keys to change — it is
deep-merged over the bundled `pull_up.yaml`:

```yaml
# ~/.bar-scheduler/exercises/pull_up.yaml
test_frequency_weeks: 4
session_params:
  S:
    rest_min: 120
```

---

## Complete worked example: adding a custom exercise "ring_row"

### 1. Create `~/.bar-scheduler/exercises/ring_row.yaml`

```yaml
exercise_id: ring_row
display_name: "Ring Row"
muscle_group: upper_pull

bw_fraction: 0.60       # ~60% BW at 45-degree body angle
load_type: bw_plus_external

variants: [horizontal, incline_45, incline_30]
primary_variant: horizontal
variant_factors:
  horizontal: 1.00
  incline_45: 0.85
  incline_30: 0.70

has_variant_rotation: true
grip_cycles:
  S: [horizontal, incline_45, incline_30]
  H: [horizontal, incline_45]
  T: [horizontal]
  E: [horizontal]
  TEST: [horizontal]

level_thresholds: [6, 15, 25]
set_fatigue_curve: [1.0, 0.85, 0.75, 0.68, 0.63]

session_params:
  S:
    reps_fraction_low: 0.40
    reps_fraction_high: 0.60
    reps_min: 5
    reps_max: 10
    rest_min: 120
    rest_max: 240
    rir_target: 2
    sets_by_level: [2, 3, 4, 5]
  H:
    reps_fraction_low: 0.60
    reps_fraction_high: 0.80
    reps_min: 8
    reps_max: 15
    rest_min: 90
    rest_max: 150
    rir_target: 2
    sets_by_level: [2, 3, 4, 5]
  E:
    reps_fraction_low: 0.40
    reps_fraction_high: 0.60
    reps_min: 8
    reps_max: 20
    sets_min: 5
    sets_max: 8
    rest_min: 45
    rest_max: 75
    rir_target: 3
  T:
    reps_fraction_low: 0.25
    reps_fraction_high: 0.45
    reps_min: 3
    reps_max: 6
    rest_min: 60
    rest_max: 120
    rir_target: 4
  TEST:
    reps_fraction_low: 1.0
    reps_fraction_high: 1.0
    reps_min: 1
    reps_max: 50
    sets_min: 1
    sets_max: 1
    rest_min: 180
    rest_max: 300
    rir_target: 0

target_metric: max_reps
target_value: 25.0

test_protocol: |
  RING ROW MAX REP TEST
  Setup: rings at hip height, body at ~45 degrees.
  Warm-up: 5 easy rows, rest 2 min.
  Test: pull until chest touches rings, lower to full extension. Clean reps only.
test_frequency_weeks: 3

onerm_includes_bodyweight: true
onerm_explanation: >
  Ring row 1RM uses 60% of bodyweight as the working load.

weight_increment_fraction: 0.01
weight_tm_threshold: 10
max_added_weight_kg: 20.0

default_item: BAR_ONLY
equipment:
  BAR_ONLY:
    label: "Rings (bodyweight)"
    assistance_kg: 0.0
    requires_weight_declaration: false
```

### 2. Enable it for a user (via the public API)

```python
from pathlib import Path
from bar_scheduler import api

data_dir = Path("~/.bar-scheduler").expanduser()
api.enable_exercise(data_dir, "ring_row", days_per_week=3)
```

`registry.get_exercise("ring_row")` and `api.get_plan(data_dir, "ring_row")` now
work with full variant rotation and session parameters — no code changes
required.
