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
| `init` | Initialize profile and history file (preserves existing history) |
| `plan` | Unified history + upcoming plan with progressive TM |
| `log-session` | Log a completed session |
| `show-history` | Display training history |
| `plot-max` | ASCII chart of max reps progress (`--trajectory` overlays planned growth line) |
| `update-weight` | Update current bodyweight |
| `delete-record N` | Delete history entry #N (shown in plan `#` column) |
| `status` | Show current training status |
| `volume` | Show weekly volume chart |
| `explain DATE` | Step-by-step breakdown of how a session's parameters were calculated |
| `1rm` | Estimate 1-rep max using the Epley formula |

## Multi-Exercise Support

All data commands accept `--exercise` / `-e` to select an exercise (default: `pull_up`):

```bash
# Dip plan
bar-scheduler plan --exercise dip

# Log a dip session (shows standard/chest_lean/tricep_upright variants)
bar-scheduler log-session --exercise dip

# BSS status
bar-scheduler status --exercise bss

# Estimate pull-up 1RM
bar-scheduler 1rm

# BSS 1RM (external load only — no bodyweight included)
bar-scheduler 1rm --exercise bss
```

Separate history files are used per exercise:
- Pull-up: `~/.bar-scheduler/history.jsonl` (legacy) or `pull_up_history.jsonl`
- Dip: `~/.bar-scheduler/dip_history.jsonl`
- BSS: `~/.bar-scheduler/bss_history.jsonl`

See [docs/exercises/](docs/exercises/) for per-exercise biomechanics, variant
details, and test protocols. All three protocols are also summarised in
[docs/assessment_protocols.md](docs/assessment_protocols.md).

## JSON Output

Add `--json` (or `-j`) to any data command for machine-readable output (plain stdout, no colour):

```bash
bar-scheduler status --json
bar-scheduler plan --json
bar-scheduler show-history --json
bar-scheduler volume --json
bar-scheduler plot-max --json
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

Comma-separated individual sets (all sets specified independently):

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

## Plan Output

The `plan` command shows a unified table of past sessions and future sessions:

```
Current status
- Training max (TM): 9
- Latest test max: 10
...

 ✓  #  Wk  Date        Type  Grip        Prescribed          Actual          TM
 ✓   1   1  2026-02-01  TEST  pronated    1x max reps         10 reps (max)    9
 ✓   2   1  2026-02-04  S     neutral     5x4 / 240s          5+5+5+4 = 19     9
 >      2  2026-02-06  H     supinated   6x5 / 120s                           9
            2  2026-02-09  E     pronated    4, 3×8 / 60s                          9

Prescribed: 5x4 = 5 reps × 4 sets  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3, 60s rest before each set
```

Columns:
- **✓ / >** — done / next session
- **#** — history ID (use with `delete-record N`)
- **Wk** — week number
- **Prescribed** — planned sets (`5x4` = 5 reps × 4 sets; `4, 3×8 / 60s` = 1×4 + 8×3, 60 s rest)
- **Actual** — what was actually done
- **TM** — expected Training Max after this session

Grip rotates automatically: S/H cycle pronated → neutral → supinated, T alternates pronated/neutral.

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

## Session Types

| Type | Description | Reps | Rest | Grip rotation |
|------|-------------|------|------|---------------|
| S | Strength | 4-6 | 180-300 s | pronated → neutral → supinated |
| H | Hypertrophy | 6-12 | 90-150 s | pronated → neutral → supinated |
| E | Endurance/Density | 3-8 | 45-75 s | pronated (fixed) |
| T | Technique | 2-4 | 60-120 s | pronated → neutral |
| TEST | Max test | max | 180 s | pronated (fixed) |

## Explain Command

`explain` shows a step-by-step breakdown of every parameter in a planned session:

```bash
bar-scheduler explain next          # next upcoming session
bar-scheduler explain 2026-02-22    # specific date
```

Output includes: session type selection, grip rotation math, TM weekly progression, sets/reps calculation, added weight formula, rest midpoint, and expected TM after the session.

## Interactive Menu

Running `bar-scheduler` without arguments opens the interactive menu:

```
[1] Show plan        [2] Log session
[3] Show history     [4] Status / plots
[5] Current status   [6] Update bodyweight
[e] Explain how a session was planned
[i] Setup / edit profile
[d] Delete a session by ID
[0] Quit
```

All menu options prompt interactively — no flags required.

Logging a session via the menu walks you through each step interactively.

## Overperformance Detection

If the best set in a session exceeds the current test max (BW or weighted equivalent), a TEST session is auto-logged silently and a "New personal best!" message is shown. The plan TM updates on the next `plan` run.

## Running Tests

```bash
uv run pytest
```

## Documentation

- [Training Model](docs/training_model.md) - formulas and adaptation logic (summary)
- [CLI Examples](docs/cli_examples.md) - CLI usage examples
- [Core Training Formulas](core_training_formulas_fatigue.md) - detailed mathematical model specification
- [References](REFERENCES.md) - scientific sources and citations

## Project Structure

```
bar-scheduler/
├── pyproject.toml
├── README.md
├── REFERENCES.md                    # Scientific citations
├── core_training_formulas_fatigue.md # Detailed model spec
├── docs/
│   ├── training_model.md
│   └── cli_examples.md
├── src/bar_scheduler/
│   ├── core/
│   │   ├── config.py      # All constants (tunable)
│   │   ├── models.py      # Dataclasses
│   │   ├── metrics.py     # Pure functions
│   │   ├── physiology.py  # Fitness-fatigue model
│   │   ├── adaptation.py  # Plateau/deload logic
│   │   ├── planner.py     # Plan generation
│   │   └── ascii_plot.py  # ASCII plotting
│   ├── io/
│   │   ├── serializers.py # JSON serialization
│   │   └── history_store.py # JSONL storage
│   └── cli/
│       ├── main.py        # Typer CLI + interactive menu
│       └── views.py       # Rich formatting
└── tests/
    └── test_cli_smoke.py  # Smoke tests
```

## License

This software is licensed under CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 International).

- **Commercial use is not permitted.**
- **Non-commercial use requires attribution** with a direct link to the original repository.

See [LICENSE](LICENSE) for full terms.
