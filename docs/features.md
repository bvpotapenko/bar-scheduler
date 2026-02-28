# bar-scheduler — Feature List

This document lists all implemented features grouped by area. Intended for project managers and stakeholders to understand what the tool currently does. Update this file whenever a new feature is added or removed.

---

## 1. Profile & Onboarding

| # | Feature | CLI command |
|---|---------|-------------|
| 1.1 | Create / update user profile (height, sex, bodyweight, target reps, training days) | `init` |
| 1.2 | Per-exercise training days 1–5 days/week (separate schedule for pull_up / dip / bss) | `init --exercise <id> --days-per-week N` |
| 1.3 | Baseline max test logged on first init | `init --baseline-max N` |
| 1.4 | Update bodyweight (auto-updates after every logged session too) | `update-weight` |
| 1.5 | Profile fields: exercises_enabled, max_session_duration_minutes, rest_preference, injury_notes | stored in `profile.json` |
| 1.6 | Profile changes shown as diff when re-running init | `init` |
| 1.7 | Interactive setup wizard (menu option `[i]`) | interactive menu |

## 2. Training Log (Session Logging)

| # | Feature | CLI command |
|---|---------|-------------|
| 2.1 | Log a completed session (date, bodyweight, grip, type, sets) | `log-session` |
| 2.2 | Interactive step-by-step session entry with per-set validation | `log-session` (no flags) |
| 2.3 | Exercise selection prompt in interactive mode (pull_up / dip / bss) | interactive log |
| 2.4 | Compact set format: `4x5 +2kg / 240s` expands to individual sets | `--sets "4x5 +2kg / 240s"` |
| 2.5 | Per-set format: `reps@weight/rest`, `reps weight rest`, or bare `reps` | `--sets` |
| 2.6 | Default rest of 180 s when rest is omitted | automatic |
| 2.7 | Reps-in-reserve (RIR) capture for adaptive planning | `--rir N` or interactive prompt |
| 2.8 | Session notes | `--notes` or interactive prompt |
| 2.9 | Overperformance detection — reps > test_max auto-logs a TEST session | automatic |
| 2.10 | Personal best notification with new TM displayed | automatic |
| 2.11 | Delete a logged session by ID | `delete-record N` or menu `[d]` |
| 2.12 | JSON output for machine processing | `log-session --json` |
| 2.13 | Grip/variant always "standard" for dips (no prompt) | automatic |
| 2.14 | Plan prescription auto-attached from plan cache at log time | automatic |

## 3. Training Plan

| # | Feature | CLI command |
|---|---------|-------------|
| 3.1 | Unified plan/history timeline — past (actual) and future (planned) in one table | `plan` |
| 3.2 | Immutable past prescriptions (frozen when logged; never regenerated) | automatic |
| 3.3 | Multi-week plan with configurable horizon | `plan --weeks N` |
| 3.4 | Session rotation: S (1-day); S→H (2-day); S→H→E (3-day); S→H→T→E (4-day); S→H→T→E→S (5-day) | automatic |
| 3.5 | Training max (TM) = 90% of latest TEST session | automatic |
| 3.6 | Weekly TM progression — nonlinear curve, slows near target | automatic |
| 3.7 | Autoregulation: sets/reps adjusted by readiness z-score (active after ≥10 sessions) | automatic |
| 3.8 | Adaptive rest — midpoint adjusted ±30/15 s based on last session's RIR and drop-off | automatic |
| 3.9 | Added weight for Strength sessions (BW-relative formula, 0.5 kg increments) | automatic |
| 3.10 | Endurance session volume scales with TM (kE multiplier) | automatic |
| 3.11 | TEST session insertion every N weeks per exercise protocol | automatic |
| 3.12 | Grip rotation across sessions (pronated → neutral → supinated for pull-ups) | automatic |
| 3.13 | Deload detection: triggers on plateau + low readiness, underperformance, or low compliance | automatic |
| 3.14 | Plan change notifications — diff printed when plan shifts between runs | `plan` |
| 3.15 | Plan start date anchored per-exercise in profile; only REST records (from `skip`) advance the anchor — training sessions do not | `skip` |
| 3.16 | Cumulative week numbering from first session in history | automatic |
| 3.17 | BSS band progression note when next band level is achievable | automatic |
| 3.18 | Overtraining detection — graduated warning + volume/rest/rep reduction at levels 1–3; first future session shifted forward by extra_rest_days (level ≥2) without writing REST records | automatic, shown before plan |
| 3.19 | RIR feedback: RIR=4+ sessions accumulate less fatigue than RIR=3 (sub-neutral multiplier); prevents false overtraining warnings for easy sessions | automatic |

## 4. Plan Explanation

| # | Feature | CLI command |
|---|---------|-------------|
| 4.1 | Step-by-step explanation of any date: planned session, rest day within horizon, or historical session | `explain YYYY-MM-DD` or `explain next` |
| 4.2 | TM formula and weekly progression log | `explain` output |
| 4.3 | Sets range explained: midpoint is target; autoregulation reduces (never exceeds) | `explain` output |
| 4.4 | Adaptive rest explained: base midpoint ± adjustments from last same-type session | `explain` output |
| 4.5 | Grip cycle and modular arithmetic shown | `explain` output |
| 4.6 | Added weight formula step-by-step | `explain` output |
| 4.7 | Endurance volume (kE) breakdown | `explain` output |
| 4.8 | Interactive explain from menu — uses the current exercise (no pull-up cross-contamination) | menu `[e]` |
| 4.9 | Overtraining shift notice shown at top of explain when plan start was pushed forward | `explain` output |

## 5. Status & Analysis

| # | Feature | CLI command |
|---|---------|-------------|
| 5.1 | Current status: TM, latest TEST, readiness z-score, plateau/deload flags | `status` |
| 5.2 | Weekly volume chart (ASCII bar chart) | `volume` |
| 5.3 | ASCII progress chart of max reps over time | `plot-max` |
| 5.4 | Trajectory overlays: z = BW reps (·), g = goal-weight reps (×), m = 1RM added kg (○) | `plot-max -t z/g/m` or combined `-t zmg` |
| 5.4a | `m` trajectory uses rep-range–aware blended formula (Brzycki/Lander/Lombardi/Epley); capped at r=20 | automatic |
| 5.4b | Independent right axis for `m` trajectory (kg scale, not tied to left-axis reps) | automatic |
| 5.5 | 1RM estimation — all 5 formulas (Epley, Brzycki, Lander, Lombardi, Blended) with ★ best-formula marker | `1rm` |
| 5.6 | Track B max estimators: FI method (Pekünlü 2013) + Nuzzo 2024 | automatic, shown in plan |
| 5.7 | eMax column in plan: TEST → actual max; non-TEST → FI/Nuzzo estimate | `plan` output |
| 5.8 | Show full session history as table | `show-history` |
| 5.9 | History limit filter | `show-history --limit N` |
| 5.10 | History JSON export | `show-history --json` |

## 6. Adaptation Guide

| # | Feature | CLI command |
|---|---------|-------------|
| 6.1 | Built-in adaptation timeline (Day 1 through Weeks 12+) with what to expect | `help-adaptation` |
| 6.2 | Interactive menu shortcut | menu `[a]` |

## 7. Multi-Exercise Support

| # | Feature | CLI command |
|---|---------|-------------|
| 7.1 | Three exercises: Pull-Up, Parallel Bar Dip, Bulgarian Split Squat | `--exercise pull_up/dip/bss` |
| 7.2 | Separate history files per exercise (`pull_up_history.jsonl`, `dip_history.jsonl`, `bss_history.jsonl`) | automatic routing |
| 7.3 | Global `-e`/`--exercise` flag sets default exercise for entire interactive session | `bar-scheduler -e dip` |
| 7.4 | Exercise-specific TM, added weight, and session parameters | automatic |
| 7.5 | BSS external-only load model (dumbbell weight from last TEST) | automatic |
| 7.6 | Effective load (Leff) respects bodyweight fraction per exercise | automatic |
| 7.7 | `(per leg)` suffix shown for BSS sessions in plan table | automatic |

## 8. Equipment Management

| # | Feature | CLI command |
|---|---------|-------------|
| 8.1 | Equipment catalog per exercise (bands, machine, elevation for BSS) | `update-equipment` |
| 8.2 | Equipment history with valid-from / valid-until timestamps | automatic |
| 8.3 | Leff change notification when active equipment changes ≥10% | automatic |
| 8.4 | Band progression suggestion when consecutive sessions at current band | automatic |
| 8.5 | BSS degraded warning when no elevation surface is configured | automatic |
| 8.6 | Equipment snapshot attached to each logged session | automatic |
| 8.7 | Available items multi-select; active item single-select with clear prompt | `update-equipment` |

## 9. Configuration & Customisation

| # | Feature | CLI command |
|---|---------|-------------|
| 9.1 | All model constants in `exercises.yaml` (bundled with package) | — |
| 9.2 | User override at `~/.bar-scheduler/exercises.yaml` (deep-merge with defaults) | file override |
| 9.3 | YAML loader with graceful fallback to Python constants if PyYAML not installed | automatic |

## 10. UX & Output

| # | Feature | CLI command |
|---|---------|-------------|
| 10.1 | Rich-formatted tables and coloured terminal output | all commands |
| 10.2 | Dynamic grip legend (only shows variants present in the current plan) | `plan` |
| 10.3 | Compact set notation in plan table: `4×5 / 240s`, `4, 3×8 / 60s` | `plan` |
| 10.4 | Actual session shows rest times per-set or as single value when uniform | `plan` |
| 10.5 | Interactive main menu with numbered/lettered shortcuts | `bar-scheduler` (no args) |
| 10.6 | JSON output mode for scripting | `--json` on most commands |
| 10.7 | Skip command to shift the **plan** forward (N>0) or backward (N<0) by N **calendar days**. Forward: inserts N plan-REST records starting at `from_date`, pushing all future sessions later. Backward: removes plan-REST records in the gap `[from_date−N, from_date)` and sets plan anchor to `from_date−N`, pulling future sessions earlier. **Never modifies user-submitted training logs** — only plan-REST records created by `skip` are added/removed; use `delete-record` to modify training logs. Logged training sessions never auto-advance the plan anchor. | `skip` |
| 10.8 | Plan cache for change detection between runs | automatic |

---

*Last updated: 2026-02-28 (skip backward fix: plan anchor, REST gap cleanup, invariant docs; Monday-anchored week numbers; exercise_id in delete-record; overtraining cutoff for far-future explain). Keep this file current: update after every feature addition, change, or removal.*
