# bar-scheduler

Evidence-informed pull-up training planner to reach 30 strict pull-ups.

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
| `plot-max` | ASCII chart of max reps progress |
| `update-weight` | Update current bodyweight |
| `delete-record N` | Delete history entry #N (shown in plan `#` column) |
| `status` | Show current training status |
| `volume` | Show weekly volume chart |

## Sets Format

When logging sessions, use either format per set (sets are comma-separated):

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
- `8@0/180, 6@0/120, 5@0` — three sets (rest optional on last)
- `8 0 180, 6 0 120, 5 0` — same in space format

## Plan Output

The `plan` command shows a unified table of past sessions and future sessions:

```
Current status
- Training max (TM): 9
- Latest test max: 10
...

 ✓  #  Wk  Date        Type  Grip        Prescribed          Actual          TM
 ✓   1   1  2026-02-01  TEST  pronated    1x max reps         10 reps (max)    9
 ✓   2   1  2026-02-04  S     neutral     4x5 / 240s          5+5+5+4 = 19     9
 >      2  2026-02-06  H     supinated   5x6 / 120s                           9
            2  2026-02-09  E     pronated    4, 3×8 / 60s                          9

Prescribed: 4x5 = 4 sets × 5 reps  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3, 60s rest before each set
```

Columns:
- **✓ / >** — done / next session
- **#** — history ID (use with `delete-record N`)
- **Wk** — week number
- **Prescribed** — planned sets (`4x5` = 4×5 reps; `4, 3×8 / 60s` = 1×4 + 8×3, 60 s rest)
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

## Interactive Menu

Running `bar-scheduler` without arguments opens the interactive menu:

```
[1] Show plan        [2] Log session
[3] Show history     [4] Status / plots
[i] Setup / edit profile
[d] Delete a session by ID
[q] Quit
```

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
