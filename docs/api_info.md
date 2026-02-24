# bar-scheduler JSON API

All commands that produce data support a `--json` (`-j`) flag that writes a single JSON object or array to **stdout** (no Rich markup, no colour). Use this to integrate bar-scheduler with scripts, dashboards, or other tools.

Errors are always written to **stderr** in plain text even when `--json` is active.

---

## `status --json`

Returns current training status.

```bash
bar-scheduler status --json
bar-scheduler status --exercise dip --json
```

```json
{
  "training_max": 10,
  "latest_test_max": 12,
  "trend_slope_per_week": 0.45,
  "is_plateau": false,
  "deload_recommended": false,
  "readiness_z_score": 0.23,
  "fitness": 1.4832,
  "fatigue": 0.6201
}
```

| Field | Type | Description |
|-------|------|-------------|
| `training_max` | int | Current TM = floor(0.9 × test_max) — conventional definition |
| `latest_test_max` | int \| null | Most recent TEST session max reps |
| `trend_slope_per_week` | float | Linear regression slope of test-max data (reps/week) |
| `is_plateau` | bool | True if slope below threshold for plateau window |
| `deload_recommended` | bool | True if deload criteria met |
| `readiness_z_score` | float | Fitness-fatigue model z-score (autoregulation input) |
| `fitness` | float | G(t) — slow-decay fitness component |
| `fatigue` | float | H(t) — fast-decay fatigue component |

---

## `show-history --json`

Returns an array of logged sessions, oldest first.

```bash
bar-scheduler show-history --json
bar-scheduler show-history --limit 5 --json
bar-scheduler show-history --exercise dip --json
```

```json
[
  {
    "date": "2026-02-01",
    "session_type": "TEST",
    "grip": "pronated",
    "bodyweight_kg": 82.0,
    "exercise_id": "pull_up",
    "total_reps": 10,
    "max_reps": 10,
    "avg_rest_s": 180,
    "sets": [
      { "reps": 10, "weight_kg": 0.0, "rest_s": 180 }
    ]
  },
  {
    "date": "2026-02-04",
    "session_type": "S",
    "grip": "neutral",
    "bodyweight_kg": 82.0,
    "exercise_id": "pull_up",
    "total_reps": 19,
    "max_reps": 5,
    "avg_rest_s": 240,
    "sets": [
      { "reps": 5, "weight_kg": 0.5, "rest_s": 240 },
      { "reps": 5, "weight_kg": 0.5, "rest_s": 240 },
      { "reps": 5, "weight_kg": 0.5, "rest_s": 240 },
      { "reps": 4, "weight_kg": 0.5, "rest_s": 240 }
    ]
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | ISO date YYYY-MM-DD |
| `session_type` | string | `S`, `H`, `E`, `T`, or `TEST` |
| `grip` | string | e.g. `pronated`, `neutral`, `supinated`, `standard` |
| `bodyweight_kg` | float | Bodyweight at time of session |
| `exercise_id` | string | Exercise identifier: `pull_up`, `dip`, or `bss` |
| `total_reps` | int | Sum of actual reps across all sets |
| `max_reps` | int | Best single set (bodyweight-equivalent) |
| `avg_rest_s` | int | Average rest between sets (seconds) |
| `sets[].reps` | int | Actual reps performed |
| `sets[].weight_kg` | float | Added weight (0 = bodyweight only) |
| `sets[].rest_s` | int | Rest before this set (seconds) |

---

## `plan --json`

Returns the current training status plus the full unified timeline (past sessions + upcoming plan).

**Note:** The `eMax` column shown in the plan table is display-only and is not present in the JSON output. The `expected_tm` field is the machine-readable equivalent for future sessions.

```bash
bar-scheduler plan --json
bar-scheduler plan -w 8 --json
bar-scheduler plan --exercise dip --json
```

```json
{
  "status": {
    "training_max": 9,
    "latest_test_max": 10,
    "trend_slope_per_week": 0.0,
    "is_plateau": false,
    "deload_recommended": false,
    "readiness_z_score": 0.12
  },
  "plan_changes": ["2026-02-11 S: 4→5 sets", "2026-02-17 E: TM 9→10"],
  "sessions": [
    {
      "date": "2026-02-01",
      "week": 1,
      "type": "TEST",
      "grip": "pronated",
      "status": "done",
      "id": 1,
      "exercise_id": "pull_up",
      "expected_tm": 9,
      "prescribed_sets": [
        { "reps": 10, "weight_kg": 0.0, "rest_s": 180 }
      ],
      "actual_sets": [
        { "reps": 10, "weight_kg": 0.0, "rest_s": 180 }
      ]
    },
    {
      "date": "2026-02-08",
      "week": 2,
      "type": "E",
      "grip": "pronated",
      "status": "next",
      "id": null,
      "exercise_id": "pull_up",
      "expected_tm": 9,
      "prescribed_sets": [
        { "reps": 4, "weight_kg": 0.0, "rest_s": 60 },
        { "reps": 3, "weight_kg": 0.0, "rest_s": 60 },
        { "reps": 3, "weight_kg": 0.0, "rest_s": 60 }
      ],
      "actual_sets": null
    }
  ]
}
```

### `status` fields

Same as `status --json` (without `fitness`/`fatigue`).

### `plan_changes` field

Array of human-readable strings describing what changed vs the previous `plan` run. Empty array `[]` if nothing changed or on the first run. Examples:

- `"New: 2026-02-22 S"` — a new session was added to the plan
- `"Removed: 2026-02-22 S"` — a session was removed
- `"2026-02-11 S: 4→5 sets"` — set count changed
- `"2026-02-11 S: 5→6 reps, TM 9→10"` — multiple fields changed in one session

### `sessions[]` fields

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | ISO date YYYY-MM-DD |
| `week` | int | Week number in the plan (1-indexed; 0 = unplanned extra) |
| `type` | string | Session type: `S`, `H`, `E`, `T`, or `TEST` |
| `grip` | string | Grip for this session |
| `status` | string | `done`, `next`, `planned`, `missed`, or `extra` |
| `id` | int \| null | History ID (for `delete-record N`); null for future sessions |
| `exercise_id` | string | Exercise identifier: `pull_up`, `dip`, or `bss` |
| `expected_tm` | int \| null | Projected TM for this session (used to compute eMax for display) |
| `prescribed_sets` | array \| null | Planned sets; null for unplanned extra sessions |
| `actual_sets` | array \| null | What was actually done; null for future sessions |

---

## `volume --json`

Returns weekly total rep counts.

```bash
bar-scheduler volume --json
bar-scheduler volume -w 8 --json
```

```json
{
  "weeks": [
    { "label": "3 weeks ago", "total_reps": 85 },
    { "label": "2 weeks ago", "total_reps": 115 },
    { "label": "Last week",   "total_reps": 128 },
    { "label": "This week",   "total_reps": 42  }
  ]
}
```

Array is ordered oldest → newest. `total_reps` is 0 for weeks with no sessions.

---

## `plot-max --json`

Returns the raw TEST session data points used by the progress chart.

```bash
bar-scheduler plot-max --json
bar-scheduler plot-max --trajectory --json
```

```json
{
  "data_points": [
    { "date": "2026-02-01", "max_reps": 10 },
    { "date": "2026-03-15", "max_reps": 12 },
    { "date": "2026-05-01", "max_reps": 16 }
  ],
  "trajectory": [
    { "date": "2026-02-01", "projected_max": 10.0 },
    { "date": "2026-02-08", "projected_max": 10.78 },
    { "date": "2026-02-15", "projected_max": 11.54 }
  ]
}
```

`data_points` is ordered chronologically. Only TEST sessions with at least 1 rep are included.

`trajectory` is `null` when `--trajectory` flag is not given. When present, it contains weekly projected max reps from the first test date to the target, computed using the model's progression formula.

---

## `log-session --json`

Log a session and receive a JSON summary. All interactive prompts still run normally when options are omitted — only the final output is JSON.

```bash
bar-scheduler log-session \
  --date 2026-02-18 --bodyweight-kg 82 \
  --grip pronated --session-type S \
  --sets "5x4 +0.5kg / 240s" \
  --json
```

```json
{
  "date": "2026-02-18",
  "session_type": "S",
  "grip": "pronated",
  "bodyweight_kg": 82.0,
  "exercise_id": "pull_up",
  "total_reps": 20,
  "max_reps_bodyweight": 0,
  "max_reps_equivalent": 5,
  "new_personal_best": false,
  "new_tm": null,
  "sets": [
    { "reps": 5, "weight_kg": 0.5, "rest_s": 240 },
    { "reps": 5, "weight_kg": 0.5, "rest_s": 240 },
    { "reps": 5, "weight_kg": 0.5, "rest_s": 240 },
    { "reps": 5, "weight_kg": 0.5, "rest_s": 240 }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Session date |
| `session_type` | string | Session type logged |
| `grip` | string | Grip used |
| `bodyweight_kg` | float | Bodyweight logged |
| `exercise_id` | string | Exercise identifier |
| `total_reps` | int | Total reps across all sets |
| `max_reps_bodyweight` | int | Best bodyweight-only set (0 if weighted throughout) |
| `max_reps_equivalent` | int | Best BW-equivalent rep count (same as above when no added weight) |
| `new_personal_best` | bool | True if a new TEST session was auto-logged |
| `new_tm` | int \| null | New training max if personal best, otherwise null |
| `sets[].reps` | int | Reps in this set |
| `sets[].weight_kg` | float | Added weight (0 = bodyweight only) |
| `sets[].rest_s` | int | Rest before this set (seconds) |

---

## `1rm --json`

Estimate 1-rep max from recent training sessions using the Epley formula.

```bash
bar-scheduler 1rm --json
bar-scheduler 1rm --exercise bss --json
```

```json
{
  "exercise_id": "pull_up",
  "epley_1rm_kg": 102.7,
  "best_set_reps": 5,
  "best_set_load_kg": 82.5,
  "sessions_scanned": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `exercise_id` | string | Exercise the estimate applies to |
| `epley_1rm_kg` | float | Estimated 1-rep max in kg (Epley formula: `load × (1 + reps/30)`) |
| `best_set_reps` | int | Reps from the set that produced the highest 1RM estimate |
| `best_set_load_kg` | float | Total load used for that set (BW + added weight; BSS = added weight only) |
| `sessions_scanned` | int | Number of recent sessions examined (up to 5) |

Returns `null` (with a non-zero exit code) if no eligible sets are found in the scan window.

---

## `profile.json` Structure

The profile is stored at `~/.bar-scheduler/profile.json`. Key fields:

```json
{
  "height_cm": 180,
  "sex": "male",
  "preferred_days_per_week": 3,
  "target_max_reps": 30,
  "current_bodyweight_kg": 82.0,
  "plan_start_date": "2026-02-20",
  "exercise_days": { "pull_up": 3, "dip": 4 }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `height_cm` | int | Used for biomechanical scaling |
| `sex` | string | `male` or `female` |
| `preferred_days_per_week` | int | Default training frequency (fallback for exercises not in `exercise_days`) |
| `target_max_reps` | int | Long-term goal; used by progression formula |
| `current_bodyweight_kg` | float | Auto-updated after each logged session |
| `plan_start_date` | string | ISO date when the plan starts; updated by `init` and `skip` |
| `exercise_days` | dict | Per-exercise days-per-week overrides; e.g. `{"pull_up": 3, "dip": 4}` |

`exercise_days` is optional. If an exercise is not listed, `preferred_days_per_week` is used as the fallback via `profile.days_for_exercise(exercise_id)`.

---

## Integration Examples

```bash
# Get current TM in a shell script
TM=$(bar-scheduler status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['training_max'])")
echo "Training max: $TM"

# Export history to CSV (via jq)
bar-scheduler show-history --json \
  | jq -r '.[] | [.date, .session_type, .total_reps, .max_reps] | @csv'

# Get next session date
bar-scheduler plan --json \
  | jq -r '.sessions[] | select(.status == "next") | .date'

# Weekly reps last 8 weeks
bar-scheduler volume -w 8 --json | jq '.weeks[] | "\(.label): \(.total_reps)"'

# Estimated 1RM as a plain number
bar-scheduler 1rm --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['epley_1rm_kg'])"
```
