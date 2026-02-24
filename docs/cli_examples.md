# CLI Examples

This document shows example commands and output for bar-scheduler.

## Interactive Menu

Running `bar-scheduler` without arguments opens the interactive menu — the easiest way to use the app:

```
[1] Show training log & plan
[2] Log today's session
[3] Show full history
[4] Progress chart
[5] Current status
[6] Update bodyweight
[7] Weekly volume chart
[e] Explain how a session was planned
[r] Estimate 1-rep max
[s] Rest day — shift plan forward
[i] Setup / edit profile
[d] Delete a session by ID
[0] Quit
```

All options work interactively — no flags needed. The `[i]` option prompts for each profile field with the current value shown as default (press Enter to keep it). The `[e]` option asks for a date or accepts `next`. The `[r]` option estimates your 1-rep max from recent training sessions. The `[s]` option shifts the plan forward by one day.

## Initialize a New User

```bash
$ bar-scheduler init --height-cm 180 --sex male --days-per-week 3 --bodyweight-kg 82 --baseline-max 10

Initialized profile at /Users/you/.bar-scheduler/profile.json
History file: /Users/you/.bar-scheduler/pull_up_history.jsonl
Logged baseline test: 10 reps
Training max: 9
```

When existing history is found you are prompted to:
- **[1] Keep history** — update profile fields only (shows old → new field diff)
- **[2] Archive history** — rename to `pull_up_history_old.jsonl` and start fresh
- **[3] Cancel**

To skip the prompt: `--force`

### Per-Exercise Initialization

Use `--exercise` / `-e` to initialize a specific exercise. Each exercise stores its own history file and can have its own days-per-week setting:

```bash
# Initialize dip tracking at 4 days/week
bar-scheduler init --exercise dip --days-per-week 4 --baseline-max 8

# Initialize BSS tracking
bar-scheduler init --exercise bss --days-per-week 3 --baseline-max 12
```

## Show Training History

```bash
$ bar-scheduler show-history

  #  Date        Type  Grip        BW(kg)  Max(BW)  Total reps  Avg rest(s)
  1  2026-02-01  TEST  pronated      82.0       10          10         180
  2  2026-02-04  S     neutral       82.0        5          20         240
  3  2026-02-06  H     supinated     82.0        9          42         150
```

Use `--exercise` to show a different exercise's history:

```bash
$ bar-scheduler show-history --exercise dip --limit 5
```

## Generate Training Plan

`plan` shows past sessions and future planned sessions in a single unified table:

```bash
$ bar-scheduler plan -w 4
```

```
Current status
- Training max (TM): 9
- Latest test max: 10
- Trend (reps/week): +0.00
- Plateau: no
- Deload recommended: no
- Readiness z-score: +0.12

       Training Log
 #  Wk  Date           Type  Grip  Prescribed          Actual              eMax
  1   1  ✓ 02.01(Sun)  TST   Pro   1x max reps         10 reps (max)        10
  2   1  ✓ 02.04(Wed)  Str   Neu   5x4 / 240s          5+5+5+4 = 19 / 240s  9/10
  3   1  ✓ 02.06(Fri)  Hpy   Sup   6x5 / 120s          6+6+6+6+5 = 29 / …   9/10
  >      2  02.08(Sun) End   Pro   4, 3×8 / 60s                              10
           2  02.11(Wed) Str   Neu   5x4 / 240s                              10
           2  02.14(Fri) Hpy   Pro   6x5 / 120s                              10
           3  02.17(Sun) TST   Pro   1x max reps                             10
           ...

Type: Str=Strength  Hpy=Hypertrophy  End=Endurance  Tec=Technique  TST=Max-test  |  Grip: Pro=Pronated  Neu=Neutral  Sup=Supinated
Prescribed: 5x4 = 5 reps × 4 sets  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3  |  / Ns = N seconds rest before the set
eMax: past TEST = actual max  |  past session = FI-est/Nuzzo-est  |  future = plan projection
```

Column guide:
- **#** — history ID (use with `delete-record N`)
- **Wk** — week number in the plan
- **Date** — checkmark for completed sessions; `>` marks the next upcoming session
- **Type** — Str / Hpy / End / Tec / TST
- **Grip** — Pro=Pronated / Neu=Neutral / Sup=Supinated (pull-up); Std/CL/TUp (dip); Def/FFE (BSS)
- **Prescribed** — planned sets (`5x4` = 5 reps × 4 sets; `4, 3×8 / 60s` = 1×4 + 8×3, 60 s rest)
- **Actual** — what was logged, with per-set rests shown when they vary
- **eMax** — estimated max reps (past TEST: actual max; past training: FI-est/Nuzzo-est; future: plan projection)

Grip rotates automatically per session type:
- S and H: pronated → neutral → supinated
- T: pronated → neutral
- E and TEST: always pronated

The plan legend is dynamic — only grips that actually appear in the upcoming plan are included in the legend line.

### Plan Change Notifications

Every time you run `plan`, bar-scheduler compares the upcoming sessions to the previous run and prints a brief summary of what changed:

```
Plan updated:
  2026-02-11 S: 4→5 sets
  2026-02-17 E: TM 9→10
```

Changes are detected automatically. On the first `plan` run no diff is shown (there is no previous state to compare against).

In JSON mode (`plan --json`) the diff is returned as a `plan_changes` array:

```json
{
  "plan_changes": ["2026-02-11 S: 4→5 sets", "2026-02-17 E: TM 9→10"]
}
```

## Log a Session

```bash
$ bar-scheduler log-session \
    --date 2026-02-18 \
    --bodyweight-kg 82 \
    --grip pronated \
    --session-type S \
    --sets "5@0/180, 5@0/180, 4@0"

Logged S session for 2026-02-18
Total reps: 14
Max (bodyweight): 5
```

Use `--exercise` to log a dip or BSS session:

```bash
$ bar-scheduler log-session --exercise dip \
    --date 2026-02-18 \
    --bodyweight-kg 82 \
    --grip standard \
    --session-type H \
    --sets "8x5 / 120s"
```

BSS prescribed sets display a `(per leg)` suffix in the plan.

### Sets Format

#### Compact plan format (copy directly from the Prescribed column)

```
NxM [+Wkg] [/ Rs]
```

| Input | Meaning |
|-------|---------|
| `5x4 +0.5kg / 240s` | 5 reps × 4 sets, +0.5 kg, 240 s rest before each set |
| `6x5 / 120s` | 6 reps × 5 sets, bodyweight, 120 s rest before each set |
| `5x4` | 5 reps × 4 sets, bodyweight, 180 s rest (default) |
| `4, 3x8 / 60s` | 1 set of 4 reps + 8 sets of 3 reps, 60 s rest |

#### Per-set format (individual sets, comma-separated)

| Input | Meaning |
|-------|---------|
| `8@0/180` | 8 reps, bodyweight, 180 s rest before this set |
| `8 0 180` | same, space format |
| `5@+10/240` | 5 reps, +10 kg, 240 s rest before this set |
| `6@0` or `6 0` or `6` | 6 reps, bodyweight, 180 s rest (default) |

**Note:** rest values record time rested **before** the set, not after it.

```bash
# Compact — copy from plan output
--sets "5x4 +0.5kg / 240s"

# Per-set canonical
--sets "8@0/180, 6@0/120, 5@0"

# Per-set space format
--sets "8 0 180, 6 0 120, 5 0"
```

### Interactive Logging

Omit `--sets` to be prompted set by set. On the first prompt you can enter a compact expression and it will be expanded with a confirmation:

```
Enter sets one per line.
  Compact: NxM +Wkg / Rs  e.g. 5x4 +0.5kg / 240s  6x5 / 120s
  Per-set: reps@+weight/rest or reps weight rest  e.g. 8@0/180  8 0 180  8

  Set 1: 5x4 +0.5kg / 240s

  Compact format — 4 sets +0.5 kg, 240s rest:
    Set 1: 5 reps
    Set 2: 5 reps
    Set 3: 5 reps
    Set 4: 5 reps

  Accept? [Y/n]: Y
```

Or enter sets individually:

```
  Set 1: 8 0 180
  Set 2: 6 0 120
  Set 3: 5
  Set 4:          ← empty line to finish
```

### Bodyweight Auto-Update

The profile's `current_bodyweight_kg` is automatically updated to match the bodyweight you log with each session.

### Overperformance Detection

If the best set exceeds your current test max (bodyweight or weighted equivalent), a TEST session is auto-logged and the plan eMax updates immediately:

```bash
$ bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
    --grip pronated --session-type H --sets "12@0/120, 10@0, 9@0"

Logged H session for 2026-02-18
Total reps: 31
New personal best! Auto-logged TEST (12 reps). TM updated to 10.
```

## Skip a Day

If you need to delay training without dropping a session, shift the plan forward:

```bash
# Skip 1 day (default)
$ bar-scheduler skip

Shift plan start from 2026-02-20 to 2026-02-21? [y/N]: y
Plan start updated to 2026-02-21.

# Skip multiple days without a confirmation prompt
$ bar-scheduler skip --days 3 --force

Plan start updated to 2026-02-23.
```

`skip` updates `plan_start_date` in `profile.json`. No history is lost. Also available from the interactive menu via `[s]`.

## Estimate 1-Rep Max

```bash
$ bar-scheduler 1rm

1RM estimate (Pull-up)
- Epley 1RM: 102.7 kg
- Based on: last 5 sessions

# BSS (external load only — bodyweight not included in formula)
$ bar-scheduler 1rm --exercise bss
```

The Epley formula `1RM = load × (1 + reps/30)` is applied to each set in the last 5 sessions. The highest estimate is returned. For pull-ups and dips, total load = bodyweight + added weight. For BSS, total load = added weight only.

## Delete a Session

```bash
# Delete history entry #2 (shown in the # column of plan output)
$ bar-scheduler delete-record 2 --force

Deleted session #2 (2026-02-04 S)
```

Without `--force` you will be prompted for confirmation.

## Progress Chart

```bash
$ bar-scheduler plot-max

Max Reps Progress (Strict Pull-ups)
──────────────────────────────────────────────────────────────
 30 ┤
 22 ┤                                      ╭──● (23)
 20 ┤                                  ╭───╯
 16 ┤                      ╭──● (16)
 12 ┤          ╭──● (12)
 10 ┤      ╭───╯
  8 ● (8)──╯
──────────────────────────────────────────────────────────────
    Feb 01   Feb 15   Mar 01   Mar 15   Apr 01   Apr 15
```

### Trajectory Line

Add `--trajectory` (or `-t`) to overlay a dotted line showing the planned max reps growth from your first test to the goal:

```bash
$ bar-scheduler plot-max --trajectory

Max Reps Progress (Strict Pull-ups)
──────────────────────────────────────────────────────────────
 30 ┤                                         ········· (30)
 22 ┤                                      ╭──●
 20 ┤                                 ·····╯
 16 ┤                     ····╭──● (16)
 12 ┤         ····╭──● (12)
 10 ┤     ╭───╯
  8 ● (8)─╯
──────────────────────────────────────────────────────────────
    Feb 01   Feb 15   Mar 01
● actual max reps   · projected trajectory
```

The trajectory is calculated from your first TEST session using the model's progression formula. The trajectory field is included in `plot-max --json` when the flag is given, and `null` otherwise.

## Update Bodyweight

```bash
$ bar-scheduler update-weight --bodyweight-kg 80.5

Updated bodyweight to 80.5 kg
```

## Check Training Status

```bash
$ bar-scheduler status

Current status
- Training max (TM): 12
- Latest test max: 14
- Trend (reps/week): +0.45
- Plateau: no
- Deload recommended: no
- Readiness z-score: +0.23
```

## Weekly Volume Chart

```bash
$ bar-scheduler volume --weeks 4

Weekly Volume (Total Reps)
─────────────────────────────────────────────────
3 weeks ago │████████████████████ 85
2 weeks ago │███████████████████████████ 115
Last week   │██████████████████████████████ 128
This week   │██████████ 42
```

## Explain a Planned Session

`explain` prints a step-by-step breakdown of every parameter in a planned session — useful for understanding why the plan prescribes a specific number of sets, reps, weight, and rest.

```bash
# Explain the next upcoming session
$ bar-scheduler explain next

# Explain a specific date
$ bar-scheduler explain 2026-02-22
```

Example output:

```
Strength (S) · 2026-02-22 · Week 2, session 2/3
────────────────────────────────────────────────────

SESSION TYPE
  3-day schedule: S → H → E (repeating).
  Week 2, slot 2/3 → S.

GRIP: neutral
  S sessions rotate: pronated → neutral → supinated (3-step cycle).
  Sessions before 2026-02-22: 2 S sessions (1 in history, 1 in plan).
  2 mod 3 = 2 → neutral.

TRAINING MAX: 10
  Latest TEST: 10 reps on 2026-02-01. Starting TM = floor(0.9 × 10) = 9.
  Week 1: TM 9.00 + 0.70 = 9.70 (int = 9)
  Week 2: TM 9.70 + 0.70 = 10.40 (int = 10)
  → TM for this session: 10.

SETS: 4
  S config: sets [4–5]. Base = (4+5)//2 = 4.
  Readiness z-score: +0.15  (thresholds: low=−1.0, high=+1.0).
  z in [−1.0, +1.0] → no adjustment.
  → 4 sets.

REPS PER SET: 5
  S config: fraction [0.50–0.70] of TM, clamped to [4–6].
  Low  = max(4, int(10 × 0.50)) = 5.
  High = min(6, int(10 × 0.70)) = 6.
  Target = (5+6)//2 = 5.

ADDED WEIGHT: 0.5 kg
  TM = 10 > 9 → weight = (10 − 9) × 0.5 = 0.5 kg (cap 10 kg).

REST: 240 s
  S config: rest [180–300] s. Midpoint = (180+300)//2 = 240 s.

EXPECTED TM AFTER: 10
  Progression: 0.70 reps/week × (1/3 week) = 0.23 → int(10.40 + 0.23) = 10.
```

The `explain` command is also available from the interactive menu via `[e]`.

## JSON Output

Add `--json` (or `-j`) to any data command to get clean JSON on stdout — useful for scripting, dashboards, or piping into other tools.

```bash
# Training status as JSON
$ bar-scheduler status --json
{
  "training_max": 9,
  "latest_test_max": 10,
  "trend_slope_per_week": 0.0,
  "is_plateau": false,
  "deload_recommended": false,
  "readiness_z_score": 0.12,
  "fitness": 1.2341,
  "fatigue": 0.4102
}

# Full plan as JSON
$ bar-scheduler plan --json | jq '.sessions[] | select(.status == "next")'
{
  "date": "2026-02-08",
  "week": 2,
  "type": "E",
  "grip": "pronated",
  "status": "next",
  "id": null,
  "exercise_id": "pull_up",
  "expected_tm": 9,
  "prescribed_sets": [...],
  "actual_sets": null
}

# 1RM estimate as JSON
$ bar-scheduler 1rm --json
{
  "exercise_id": "pull_up",
  "epley_1rm_kg": 102.7,
  "best_set_reps": 5,
  "best_set_load_kg": 82.5,
  "sessions_scanned": 5
}

# Weekly volume
$ bar-scheduler volume --json
{
  "weeks": [
    { "label": "3 weeks ago", "total_reps": 85 },
    { "label": "2 weeks ago", "total_reps": 115 },
    { "label": "Last week",   "total_reps": 128 },
    { "label": "This week",   "total_reps": 42  }
  ]
}

# Log a session and capture the summary
$ bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
    --grip pronated --session-type S --sets "5x4 +0.5kg / 240s" --json
{
  "date": "2026-02-18",
  "session_type": "S",
  "grip": "pronated",
  "bodyweight_kg": 82.0,
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

Full JSON schemas and integration examples: [api_info.md](api_info.md)

## Custom History Path

All commands accept `--history-path` to use a non-default location:

```bash
$ bar-scheduler init --history-path ./my_training/history.jsonl --bodyweight-kg 82
$ bar-scheduler plan --history-path ./my_training/history.jsonl
```

## Typical Workflow

1. **init** — set up profile with your baseline max:
   ```bash
   bar-scheduler init --bodyweight-kg 82 --baseline-max 10
   ```

2. **plan** — review the 4–12 week schedule:
   ```bash
   bar-scheduler plan -w 10
   ```

3. **log-session** — record each workout:
   ```bash
   bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
       --grip pronated --session-type S --sets "5 0 240, 5 0 240, 4 0"
   ```

4. **plot-max** and **status** — track progress:
   ```bash
   bar-scheduler plot-max
   bar-scheduler status
   ```

5. **update-weight** — update bodyweight when it changes:
   ```bash
   bar-scheduler update-weight --bodyweight-kg 81
   ```

6. **skip** — push the plan forward on rest days:
   ```bash
   bar-scheduler skip
   ```

7. **plan** — regenerate weekly or after TEST sessions:
   ```bash
   bar-scheduler plan -w 8
   ```

## Model Documentation

- Full mathematical model: [core_training_formulas_fatigue.md](../core_training_formulas_fatigue.md)
- Scientific references: [REFERENCES.md](../REFERENCES.md)
