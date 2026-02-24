# bar-scheduler

Evidence-informed training planner for bodyweight strength exercises.
Supports **Pull-Up**, **Parallel Bar Dip**, and **Bulgarian Split Squat (DB)**
— all sharing one planning engine.


![Training Log](./img/training_log.png)
![Weekly Volume](./img/weekly_volume.png)
![Training Session Explained](./img/session_explained.png)

## Quickstart

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd bar-scheduler

# Install dependencies
uv sync

# Install dev dependencies for tests
uv sync --extra dev
```

### First Run

```bash
# Launch the interactive menu (recommended)
bar-scheduler

# Or use individual commands:

# Initialize profile with baseline max
bar-scheduler init --bodyweight-kg 82 --baseline-max 10

# View training plan (unified history + upcoming sessions)
bar-scheduler plan -w 10

# Log a session
bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
    --grip pronated --session-type S --sets "5@0/180, 5@0/180, 4@0"

# View history
bar-scheduler show-history

# View progress chart
bar-scheduler plot-max
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize profile and history; `--exercise` selects exercise; `--days-per-week` sets schedule |
| `plan` | Unified history + upcoming plan with progressive TM; `--weeks N`; `--json` |
| `log-session` | Log a completed session |
| `show-history` | Display training history; `--limit N` |
| `plot-max` | ASCII chart of max reps progress; `--trajectory` overlays planned growth line |
| `update-weight` | Update current bodyweight |
| `delete-record N` | Delete history entry #N (shown in plan `#` column) |
| `status` | Show current training status; `--json` |
| `volume` | Show weekly volume chart; `--weeks N`; `--json` |
| `explain DATE\|next` | Step-by-step breakdown of how a planned session was calculated |
| `skip` | Shift plan forward N days; `--days N` (default 1); `--force` |
| `update-equipment` | Update training equipment (band class, machine kg, BSS surface); `--exercise` |
| `1rm` | Estimate 1-rep max using the Epley formula; `--exercise` |
| `help-adaptation` | Show the adaptation timeline: what the model can predict at each stage |

## Multi-Exercise Support

All data commands accept `--exercise` / `-e` to select an exercise (default: `pull_up`):

```bash
# Dip plan
bar-scheduler plan --exercise dip

# Log a dip session
bar-scheduler log-session --exercise dip

# BSS status
bar-scheduler status --exercise bss

# Estimate pull-up 1RM
bar-scheduler 1rm

# BSS 1RM (external load only — bodyweight not included)
bar-scheduler 1rm --exercise bss
```

Separate history files are used per exercise:
- Pull-up: `~/.bar-scheduler/pull_up_history.jsonl`
- Dip: `~/.bar-scheduler/dip_history.jsonl`
- BSS: `~/.bar-scheduler/bss_history.jsonl`

See [docs/exercises/](docs/exercises/) for per-exercise biomechanics, variant
details, and test protocols. All three protocols are also summarised in
[docs/assessment_protocols.md](docs/assessment_protocols.md).

## Per-Exercise Training Frequency

Each exercise can have its own days-per-week setting, stored in `exercise_days` in `profile.json`:

```bash
# Set dip-specific frequency (pull-up keeps its own setting)
bar-scheduler init --exercise dip --days-per-week 4

# BSS at 3 days/week
bar-scheduler init --exercise bss --days-per-week 3
```

The `exercise_days` dict in `profile.json` stores per-exercise overrides. The `preferred_days_per_week` field acts as a fallback for any exercise not listed in `exercise_days`.

```json
{
  "preferred_days_per_week": 3,
  "exercise_days": { "pull_up": 3, "dip": 4 }
}
```

## JSON Output

Add `--json` (or `-j`) to any data command for machine-readable output (plain stdout, no colour):

```bash
bar-scheduler status --json
bar-scheduler plan --json
bar-scheduler show-history --json
bar-scheduler volume --json
bar-scheduler plot-max --json
bar-scheduler 1rm --json
bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
    --grip pronated --session-type S --sets "5x4 / 240s" --json
```

See [docs/api_info.md](docs/api_info.md) for full JSON schemas and integration examples.

## Sets Format

### Compact plan format (recommended)

Copy the `Prescribed` column directly into `--sets` or the interactive prompt:

```
NxM [+Wkg] [/ Rs]       N reps × M sets, optional weight and rest
```

Examples:
- `5x4 +0.5kg / 240s` — 4 sets of 5 reps, +0.5 kg, 240 s rest
- `6x5 / 120s` — 5 sets of 6 reps, bodyweight, 120 s rest
- `5x4` — 4 sets of 5 reps, bodyweight, 180 s rest (default)
- `4, 3x8 / 60s` — 1 set of 4 + 8 sets of 3, 60 s rest

### Per-set format

Comma-separated individual sets (each set specified independently):

```
reps@+weight/rest        canonical
reps@+weight             rest defaults to 180 s
reps weight rest         space-separated
reps weight              space-separated, rest defaults to 180 s
reps                     bare reps, bodyweight, rest 180 s
```

Examples:
- `8@0/180` or `8 0 180` — 8 reps, bodyweight, 180 s rest
- `5@+10/240` or `5 10 240` — 5 reps with +10 kg, 240 s rest
- `8@0/180, 6@0/120, 5@0` — three sets with individual rests

**Note:** rest values are the time rested **before** the set, not after it. The first set's rest is the warm-up gap before you start.

## Plan Output

The `plan` command shows a unified table of past sessions and future planned sessions:

```
 #  Wk  Date           Type  Grip  Prescribed          Actual           eMax
  1   1  ✓ 02.01(Sun)  TST   Pro   1x max reps         12 reps (max)    12
  2   1  ✓ 02.04(Wed)  Str   Neu   5x4 / 240s          5+5+4+4 = 18    11/13
  3   1  ✓ 02.06(Fri)  Hpy   Sup   6x5 / 120s          6+5+5+4+3 = 23  11/12
  >      2  02.08(Sun) End   Pro   4, 3×8 / 60s                          12
```

Legend (printed below the table):

```
Type: Str=Strength  Hpy=Hypertrophy  End=Endurance  Tec=Technique  TST=Max-test
Grip: Pro=Pronated  Neu=Neutral  Sup=Supinated
Prescribed: 5x4 = 5 reps × 4 sets  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3  |  / Ns = N seconds rest before the set
eMax: past TEST = actual max  |  past session = FI-est/Nuzzo-est  |  future = plan projection
```

Columns:
- **#** — history ID (use with `delete-record N`)
- **Wk** — week number
- **Date** — checkmark for completed sessions; `>` marks the next upcoming session
- **Type** — Str / Hpy / End / Tec / TST
- **Grip** — Pro / Neu / Sup (pull-up); Std / CL / TUp (dip); Def / FFE (BSS)
- **Prescribed** — planned sets using compact notation
- **Actual** — what was actually logged
- **eMax** — estimated max reps (see section below)

Grip rotates automatically: S/H sessions cycle pronated → neutral → supinated; T sessions alternate pronated/neutral; E and TEST are always pronated.

## Session Types

| Type | Description | Reps | Rest | Grip rotation |
|------|-------------|------|------|---------------|
| Str (S) | Strength | 4-6 | 180-300 s | pronated → neutral → supinated |
| Hpy (H) | Hypertrophy | 6-12 | 90-150 s | pronated → neutral → supinated |
| End (E) | Endurance/Density | 3-8 | 45-75 s | pronated (fixed) |
| Tec (T) | Technique | 2-4 | 60-120 s | pronated → neutral |
| TST | Max test | max | 180 s | pronated (fixed) |

## eMax Column

The **eMax** column shows estimated max reps for each row and changes meaning depending on whether the session is past or future:

- **Past TEST session** — actual max reps recorded (ground truth)
- **Past training session** — two estimates shown as `FI-est/Nuzzo-est`:
  - *FI-est*: Track B estimation using the FI method (Pekünlü & Atalağ 2013)
  - *Nuzzo-est*: estimation using Nuzzo REPS~%1RM tables (2024)
- **Future session** — plan projection: `max(round(TM / 0.9), current_test_max)` — never shown below your current max

## Interactive Menu

Running `bar-scheduler` without arguments opens the interactive menu:

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
[u] Update training equipment
[i] Setup / edit profile
[d] Delete a session by ID
[0] Quit
```

All menu options prompt interactively — no flags required. The `[i]` option prompts for each profile field with the current value shown as default (press Enter to keep it). The `[e]` option asks for a date or accepts `next`.

## Overperformance Detection

If the best set in a session exceeds the current test max (bodyweight or weighted equivalent), a TEST session is auto-logged silently and a "New personal best!" message is shown. The plan's eMax updates on the next `plan` run.

## Skip Command

If you need to take a rest day or delay training, shift the plan forward without losing the session:

```bash
# Skip 1 day (default)
bar-scheduler skip

# Skip 3 days
bar-scheduler skip --days 3

# Skip without confirmation prompt
bar-scheduler skip --days 2 --force
```

`skip` updates `plan_start_date` in `profile.json`. The plan shifts forward; no history is lost.

## Equipment Tracking

Bar-scheduler tracks what equipment you train with so that effective load (Leff)
is correctly computed across band progressions, machine-to-bar transitions, and
added-weight sessions.

### Effective Load formula

```
Pull-up / Dip:  Leff = BW × bw_fraction + added_weight_kg − assistance_kg
BSS:            Leff = 0.71 × BW + added_weight_kg   (biomechanics: lead leg bears ~71% of BW)
Weight belt:    Leff = BW + added_weight_kg           (assistance_kg = 0)
```

### Equipment options per exercise

| Exercise | Items |
|----------|-------|
| Pull-up  | Bar only · Band Light (~17 kg) · Band Medium (~35 kg) · Band Heavy (~57 kg) · Machine assisted · Weight belt |
| Dip      | Parallel bars · Band Light · Band Medium · Band Heavy · Machine assisted · Weight belt |
| BSS      | Bodyweight · Dumbbells · Barbell · Resistance band · Elevation surface (30/45/60 cm) |

### Setup

Equipment is configured during `init` or via `update-equipment`:

```bash
bar-scheduler update-equipment --exercise pull_up
```

The interactive flow asks which items you have, which you're currently using,
and for machine assistance kg or BSS elevation height where applicable.

### Band progression

When the plan detects you've consistently hit the rep ceiling for your session
type over the last 2 sessions, a suggestion appears below the plan table:

```
Ready to progress: consider stepping from Band Medium → Band Light.
```

### Leff change adjustment

When you call `update-equipment` and effective load changes by ≥ 10%, the
command prints an adjustment recommendation:

```
Equipment change detected: Leff increased ~30% → reducing reps by 20% as safety buffer.
```

### BSS without elevation surface

If ELEVATION_SURFACE is not in your available items, the plan header shows:

```
⚠ Split Squat mode — add an elevation surface to unlock BSS.
```

## Example Output

### plot-max

```
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

Add `--trajectory` to overlay the projected growth curve:

```
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

## Running Tests

```bash
uv run pytest
```

## Documentation

- [CLI Examples](docs/cli_examples.md) — commands, menu, output examples
- [Formula Reference](docs/formulas_reference.md) — all mathematical formulas with config knobs
- [JSON API](docs/api_info.md) — full JSON schemas for `--json` output
- [Training Model](docs/training_model.md) — adaptation logic summary
- [Core Training Formulas](core_training_formulas_fatigue.md) — detailed mathematical model specification
- [References](REFERENCES.md) — scientific sources and citations

## Profile Configuration

`~/.bar-scheduler/profile.json` stores your personal settings.  Key fields:

```json
{
  "height_cm": 175,
  "sex": "male",
  "preferred_days_per_week": 3,
  "target_max_reps": 30,
  "exercise_days": { "pull_up": 3, "dip": 4, "bss": 3 },
  "exercises_enabled": ["pull_up", "dip", "bss"],
  "max_session_duration_minutes": 60,
  "rest_preference": "normal",
  "injury_notes": ""
}
```

| Field | Values | Description |
|-------|--------|-------------|
| `exercises_enabled` | list of exercise IDs | Which exercises are active |
| `max_session_duration_minutes` | integer | Used in plan display notes |
| `rest_preference` | `"short"` / `"normal"` / `"long"` | Biases the adaptive-rest calculation |
| `injury_notes` | free text | Your own record; not used by the engine |

Edit this file directly, or re-run `bar-scheduler init` to update core fields while preserving custom values.

---

## Config Customisation (#14)

Model constants (time constants, progression rates, rest normalization exponents, etc.)
are documented in `src/bar_scheduler/exercises.yaml`.

To customise without editing source code, create `~/.bar-scheduler/exercises.yaml`
with only the values you want to change:

```yaml
# Override example: slower fatigue decay and tighter progression
fitness_fatigue:
  TAU_FATIGUE: 5.0      # default: 7 days

progression:
  DELTA_PROGRESSION_MAX: 0.7   # default: 1.0 reps/week
```

Any key you omit falls back to the bundled default.  Requires `PyYAML`:
```bash
pip install PyYAML
```

See [docs/training_model.md](docs/training_model.md) for the full constant reference
with YAML paths and explanations.

---

## Adaptation Timeline

The planner adapts to your data over time.  A quick summary:

| Stage | Sessions | What's active |
|-------|----------|---------------|
| Day 1 | 0 | Generic plan from baseline max; conservative volume |
| Weeks 1–2 | 3–8 | EWMA max tracking; rest normalization |
| Weeks 3–4 | 10–16 | **Autoregulation** unlocks; adaptive rest; plateau detection |
| Weeks 6–8 | 24–32 | Individual fatigue profile; deload triggers reliable |
| Weeks 12+ | 48+ | Full profile; long-term fitness curve calibrated |

```bash
bar-scheduler help-adaptation   # full guide in the terminal
```

See [docs/adaptation_guide.md](docs/adaptation_guide.md) for the complete guide.

---

## FAQ: Plan Changes

**Why did my plan change after logging a session?**

Only future sessions are regenerated.  Past prescriptions are frozen (stored in
`planned_sets` in the history file).  If you see a change in a future session,
it is because the engine updated its fitness-fatigue estimate after your new log.

**Why did the planner insert a TEST session I didn't ask for?**

The planner automatically schedules a TEST session every N weeks per exercise:
- Pull-ups and dips: every 3 weeks
- BSS: every 4 weeks

You can log the TEST session at any time; the planner will adapt from there.

**Why is my plan showing the same TM week after week?**

TM progresses once per calendar week (not once per session).  If you train 4
days in one week, all four sessions share the same TM.  Progression happens at
the next calendar-week boundary.

**How do I skip a rest day or travel week?**

```bash
bar-scheduler skip --days 7   # shift all future sessions by 7 days
```

---

## Project Structure

```
bar-scheduler/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── REFERENCES.md                         # Scientific citations
├── docs/
│   ├── training_model.md                 # Model formulas, ExerciseDefinition schema, 1RM, config
│   ├── adaptation_guide.md               # Adaptation timeline guide
│   ├── assessment_protocols.md           # Test protocols for all exercises
│   ├── cli_examples.md
│   ├── formulas_reference.md
│   ├── api_info.md
│   ├── exercises/                        # Per-exercise biomechanics docs
│   │   ├── pull_up.md
│   │   ├── dip.md
│   │   └── bss.md
│   └── references/
│       └── max_estimation.md
├── src/bar_scheduler/
│   ├── exercises.yaml            # Model constants (YAML, user-overridable)
│   ├── core/
│   │   ├── config.py             # Python constants (matches exercises.yaml)
│   │   ├── models.py             # Dataclasses
│   │   ├── metrics.py            # Pure functions
│   │   ├── physiology.py         # Fitness-fatigue model
│   │   ├── adaptation.py         # Plateau/deload logic
│   │   ├── planner.py            # Plan generation
│   │   ├── max_estimator.py      # Track B max estimation
│   │   ├── equipment.py          # Equipment / Leff calculations
│   │   ├── ascii_plot.py         # ASCII plotting
│   │   ├── exercises/            # ExerciseDefinition per exercise
│   │   │   ├── base.py           # ExerciseDefinition + SessionTypeParams
│   │   │   ├── pull_up.py
│   │   │   ├── dip.py
│   │   │   ├── bss.py
│   │   │   └── registry.py       # get_exercise()
│   │   └── engine/
│   │       └── config_loader.py  # YAML → typed config
│   ├── io/
│   │   ├── serializers.py        # JSON serialization
│   │   └── history_store.py      # JSONL storage
│   └── cli/
│       ├── main.py               # Typer CLI entry point + interactive menu
│       ├── views.py              # Rich formatting
│       └── commands/
│           ├── profile.py        # init, update-weight, update-equipment
│           ├── planning.py       # plan, explain, skip
│           ├── sessions.py       # log-session, delete-record, show-history
│           └── analysis.py       # status, volume, plot-max, 1rm, help-adaptation
└── tests/
    ├── test_cli_smoke.py         # CLI integration tests
    └── test_core_formulas.py     # Unit tests for all formulas
```

## License

This software is licensed under CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 International).

- **Commercial use is not permitted.**
- **Non-commercial use requires attribution** with a direct link to the original repository.

See [LICENSE](LICENSE) for full terms.
