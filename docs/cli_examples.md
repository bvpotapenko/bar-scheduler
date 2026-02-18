# CLI Examples

This document shows example commands and output for bar-scheduler.

## Interactive Menu

Running `bar-scheduler` without arguments opens the interactive menu — the easiest way to use the app:

```
[1] Show plan        [2] Log session
[3] Show history     [4] Status / plots
[i] Setup / edit profile
[d] Delete a session by ID
[q] Quit
```

## Initialize a New User

```bash
$ bar-scheduler init --height-cm 180 --sex male --days-per-week 3 --bodyweight-kg 82 --baseline-max 10

Initialized profile at /Users/you/.bar-scheduler/profile.json
History file: /Users/you/.bar-scheduler/history.jsonl
Logged baseline test: 10 reps
Training max: 9
```

When existing history is found you are prompted to:
- **[1] Keep history** — update profile fields only (shows old→new field diff)
- **[2] Archive history** — rename to `history_old.jsonl` and start fresh
- **[3] Cancel**

To skip the prompt: `--force`

## Show Training History

```bash
$ bar-scheduler show-history

  #  Date        Type  Grip        BW(kg)  Max(BW)  Total reps  Avg rest(s)
  1  2026-02-01  TEST  pronated      82.0       10          10         180
  2  2026-02-04  S     neutral       82.0        5          20         240
  3  2026-02-06  H     supinated     82.0        9          42         150
```

## Generate Training Plan

`plan` shows past sessions and future planned sessions in a single unified table:

```bash
$ bar-scheduler plan -w 4

Current status
- Training max (TM): 9
- Latest test max: 10
- Trend (reps/week): +0.00
- Plateau: no
- Deload recommended: no
- Readiness z-score: +0.12

       Training Log
 ✓  #  Wk  Date        Type  Grip        Prescribed        Actual          TM
 ✓   1   1  2026-02-01  TEST  pronated    1x max reps       10 reps (max)    9
 ✓   2   1  2026-02-04  S     neutral     4x5 +0.0kg / 240s 5+5+5+4 = 19    9
 ✓   3   1  2026-02-06  H     supinated   5x6 / 120s        6+6+6+6+5 = 29  9
 >       2  2026-02-08  E     pronated    4, 3×8 / 60s                       9
         2  2026-02-11  S     neutral     4x5 / 240s                         9
         2  2026-02-14  H     pronated    5x6 / 120s                         9
         3  2026-02-17  E     supinated   4, 3×8 / 60s                      10
         ...

Prescribed: 4x5 = 4 sets × 5 reps  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3, 60s rest before each set
```

Column guide:
- **✓ / >** — done / next upcoming session
- **#** — history ID (use with `delete-record N`)
- **Wk** — week number in the plan
- **Prescribed** — planned sets (`4x5` = 4 sets of 5; `4, 3×8 / 60s` = 1×4 + 8×3, 60 s rest)
- **Actual** — what was logged
- **TM** — expected Training Max after this session

Grip rotates automatically per session type:
- S and H: pronated → neutral → supinated
- T: pronated → neutral
- E and TEST: always pronated

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

### Sets Format

The `--sets` parameter accepts comma-separated sets. Each set can be written in two equivalent ways:

```
reps@+weight/rest    canonical format
reps weight rest     space-separated format
```

Rest can be omitted from any set (defaults to 180 s):

| Input | Meaning |
|-------|---------|
| `8@0/180` | 8 reps, bodyweight, 180 s rest |
| `8 0 180` | same, space format |
| `5@+10/240` | 5 reps, +10 kg, 240 s rest |
| `5 10 240` | same, space format |
| `6@0` or `6 0` or `6` | 6 reps, bodyweight, 180 s rest (default) |

Examples:
```bash
# Three sets, canonical
--sets "8@0/180, 6@0/120, 5@0"

# Three sets, space format
--sets "8 0 180, 6 0 120, 5 0"

# Weighted sets
--sets "5@+10/240, 5@+10/240, 4@+10"
```

### Interactive Logging

Omit `--sets` to be prompted set by set:

```
Enter sets one per line.
  Formats: reps@+weight/rest or reps weight rest  e.g. 8@0/180  6@+5/240  8 0 180  8

  Set 1: 8 0 180
  Set 2: 6 0 120
  Set 3: 5
  Set 4:          ← empty line to finish
```

### Overperformance Detection

If the best set exceeds your current test max (bodyweight or weighted equivalent), a TEST session is auto-logged and the plan TM updates immediately:

```bash
$ bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
    --grip pronated --session-type H --sets "12@0/120, 10@0, 9@0"

Logged H session for 2026-02-18
Total reps: 31
New personal best! Auto-logged TEST (12 reps). TM updated to 10.
```

### Bodyweight Auto-Update

The profile's `current_bodyweight_kg` is automatically updated to match the bodyweight you log with each session.

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

6. **plan** — regenerate weekly or after TEST sessions:
   ```bash
   bar-scheduler plan -w 8
   ```

## Model Documentation

- Full mathematical model: [core_training_formulas_fatigue.md](../core_training_formulas_fatigue.md)
- Scientific references: [REFERENCES.md](../REFERENCES.md)
