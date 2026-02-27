# Exercise Structure Reference

This document describes how bar-scheduler exercises are defined, how the YAML
loader works, and how to add a custom exercise or override existing values.

---

## Where exercise definitions live

```
src/bar_scheduler/exercises.yaml      ← bundled definitions (all three exercises)
~/.bar-scheduler/exercises.yaml       ← optional user overrides (deep-merged)
src/bar_scheduler/core/exercises/
  base.py        ← ExerciseDefinition + SessionTypeParams dataclasses
  loader.py      ← YAML → typed objects; falls back gracefully on failure
  registry.py    ← EXERCISE_REGISTRY dict; get_exercise() lookup function
  pull_up.py     ← Python constants (fallback if YAML unavailable)
  dip.py
  bss.py
```

At import time `registry.py` calls `load_exercises_from_yaml()`. If the YAML
is valid and PyYAML is installed, YAML values win. If anything fails, the
Python constants in `pull_up.py` / `dip.py` / `bss.py` are used instead — the
application never crashes due to a bad YAML file.

---

## ExerciseDefinition schema

Every exercise block in `exercises.yaml` must contain these fields.

| Field | Type | Description |
|-------|------|-------------|
| `exercise_id` | `str` | Unique snake_case key (e.g. `pull_up`) |
| `display_name` | `str` | Human-readable label shown in the UI |
| `muscle_group` | `str` | Informational tag (e.g. `upper_pull`, `lower`) |
| `bw_fraction` | `float` | Fraction of bodyweight that is the working load (1.0 = full BW, 0.71 = BSS lead-leg fraction) |
| `load_type` | `str` | `bw_plus_external` — weight belt / vest adds to BW load; `external_only` — only dumbbell weight, not BW |
| `variants` | `list[str]` | All valid movement variants |
| `primary_variant` | `str` | Used for standardised testing (must be in `variants`) |
| `variant_factors` | `dict[str, float]` | Relative difficulty per variant (1.0 = neutral) |
| `has_variant_rotation` | `bool` | `true` = rotate through `grip_cycles`; `false` = always use `primary_variant` |
| `grip_cycles` | `dict[str, list[str]]` | Per-session-type variant rotation order. **Omit or set to `{}`** when `has_variant_rotation: false` |
| `session_params` | `dict[str, SessionTypeParams]` | Parameters per session type (see below) |
| `target_metric` | `str` | `max_reps` or `1rm_kg` |
| `target_value` | `float` | User's long-term goal (e.g. `30` reps, `120` kg) |
| `test_protocol` | `str` | Human-readable test instructions (use YAML literal block `\|`) |
| `test_frequency_weeks` | `int` | Weeks between auto-inserted TEST sessions |
| `onerm_includes_bodyweight` | `bool` | Whether the 1RM display adds BW to the effective load |
| `onerm_explanation` | `str` | Shown by `bar-scheduler 1rm` |
| `weight_increment_fraction` | `float` | Fraction of effective BW added per TM point above threshold |
| `weight_tm_threshold` | `int` | TM must exceed this before added weight is prescribed (set to `999` to disable) |
| `max_added_weight_kg` | `float` | Hard cap on prescribed added weight |

### Optional field defaults

| Field | Default |
|-------|---------|
| `has_variant_rotation` | `true` |
| `grip_cycles` | `{}` (no rotation) |

---

## SessionTypeParams sub-schema

Each key under `session_params` maps a session type (`S`, `H`, `E`, `T`, `TEST`)
to the following nine required fields:

| Field | Type | Description |
|-------|------|-------------|
| `reps_fraction_low` | `float` | Lower fraction of TM for rep target |
| `reps_fraction_high` | `float` | Upper fraction of TM for rep target |
| `reps_min` | `int` | Absolute floor on reps per set |
| `reps_max` | `int` | Absolute ceiling on reps per set |
| `sets_min` | `int` | Minimum sets prescribed |
| `sets_max` | `int` | Maximum sets prescribed |
| `rest_min` | `int` | Minimum rest between sets (seconds) |
| `rest_max` | `int` | Maximum rest between sets (seconds) |
| `rir_target` | `int` | Reps-in-reserve target for this session type |

---

## grip_cycles rules

`grip_cycles` is a mapping from session-type string to an ordered list of
variant names. The planner keeps a per-session-type counter and picks the
variant at position `(count % len(cycle))`:

```yaml
grip_cycles:
  S: [pronated, neutral, supinated]   # cycles every 3 S sessions
  H: [pronated, neutral, supinated]
  T: [pronated, neutral]              # shorter cycle for technique sessions
  E: [pronated]                       # endurance always pronated
  TEST: [pronated]                    # tests always pronated
```

When `has_variant_rotation: false`, the planner ignores `grip_cycles`
entirely and always uses `primary_variant`. In that case, omit `grip_cycles`
or set it to `{}` to keep the YAML tidy.

---

## Validator behaviour

`loader.py` validates both levels:

1. **Missing required exercise field** — raises `ValueError` listing the absent keys.
   The registry catches this, emits a `warnings.warn`, and uses Python defaults.

2. **Missing required SessionTypeParams field** — same: `ValueError` → warning → fallback.

3. **PyYAML not installed** — `load_exercises_from_yaml()` returns `None` silently;
   Python defaults are used. No crash.

4. **YAML parse error** — `_load_yaml_file()` returns `{}`, so `load_exercises_from_yaml()`
   returns `None`; Python defaults are used.

The application will always start successfully regardless of YAML state.

---

## User override: `~/.bar-scheduler/exercises.yaml`

You can override any exercise field without editing the source code. Create (or
edit) `~/.bar-scheduler/exercises.yaml` and add an `exercises:` block. It is
**deep-merged** per-exercise-id over the bundled definitions, so you only need
to list the keys you want to change.

Example — raise the pull-up test frequency to every 4 weeks and lower the
strength-session minimum rest to 2 minutes:

```yaml
exercises:
  pull_up:
    test_frequency_weeks: 4
    session_params:
      S:
        rest_min: 120
```

---

## Complete worked example: adding a new exercise "ring_row"

### 1. Add the YAML block to `~/.bar-scheduler/exercises.yaml`

```yaml
exercises:
  ring_row:
    exercise_id: ring_row
    display_name: "Ring Row"
    muscle_group: upper_pull

    bw_fraction: 0.60       # ~60% BW at 45-degree body angle
    load_type: bw_plus_external

    variants: [horizontal, incline_45, incline_30]
    primary_variant: horizontal
    variant_factors:
      horizontal: 1.00
      incline_45: 0.85      # easier angle
      incline_30: 0.70

    has_variant_rotation: true
    grip_cycles:
      S: [horizontal, incline_45, incline_30]
      H: [horizontal, incline_45]
      T: [horizontal]
      E: [horizontal]
      TEST: [horizontal]

    session_params:
      S:
        reps_fraction_low: 0.40
        reps_fraction_high: 0.60
        reps_min: 5
        reps_max: 10
        sets_min: 3
        sets_max: 5
        rest_min: 120
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
        sets_min: 4
        sets_max: 8
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
      Test: pull until chest touches rings, lower to full extension.
      Count clean reps only.
      Log as: --exercise ring_row --session-type TEST --sets 'N@0/180'
    test_frequency_weeks: 3

    onerm_includes_bodyweight: true
    onerm_explanation: >
      Ring row 1RM uses 60% of bodyweight as the working load.
      Formula: 1RM = (0.60 x BW + added_weight) x (1 + reps/30)  [Epley].

    weight_increment_fraction: 0.01
    weight_tm_threshold: 10
    max_added_weight_kg: 20.0
```

### 2. Enable the new exercise in your profile

```bash
bar-scheduler init   # re-run; add ring_row to enabled exercises list
```

Or manually edit `~/.bar-scheduler/profile.json`:
```json
"exercises_enabled": ["pull_up", "dip", "bss", "ring_row"]
```

### 3. Verify

```bash
bar-scheduler plan -e ring_row
bar-scheduler explain next -e ring_row
```

The exercise will appear in the plan table with correct variant rotation and
session parameters immediately — no code changes required.
