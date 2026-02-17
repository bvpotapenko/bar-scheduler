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
# Initialize profile with baseline max
bar-scheduler init --bodyweight-kg 82 --baseline-max 10

# View training plan (10 weeks with progressive overload)
bar-scheduler plan -w 10

# Log a session (rest optional for last set)
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
| `plan` | Generate training plan with progressive TM |
| `log-session` | Log a completed session |
| `show-history` | Display training history |
| `plot-max` | ASCII chart of max reps progress |
| `update-weight` | Update current bodyweight |
| `status` | Show current training status |
| `volume` | Show weekly volume chart |

## Sets Format

When logging sessions, use this format:
```
reps@+weight/rest,reps@+weight/rest,...
```

Examples:
- `8@0/180` - 8 reps, bodyweight, 180s rest
- `5@+10/240` - 5 reps with +10kg, 240s rest
- `8@0/180,6@0/120,5@0` - three sets (rest optional for last set)

## Example Output

### show-history

```
Date        Type  Grip      BW(kg)  Max(BW)  Total reps  Avg rest(s)
----------  ----  --------  ------  -------  ----------  -----------
2026-02-01  TEST  pronated  82.0    10       10          180
2026-02-04  S     pronated  82.0    5        20          240
2026-02-06  H     neutral   82.0    9        42          150
```

### plan

Plan shows recent history, current position, and upcoming sessions with `>` marker:

```
Recent History
Date        Type  Grip      Sets  Total  Max
2026-02-01  TEST  pronated     1     10   10
2026-02-04  S     pronated     4     20    5

Current status
- Training max (TM): 9
- Latest test max: 10
- Trend (reps/week): +0.00
- Plateau: no
- Deload recommended: no

Last session: 2026-02-04 (S)
2 days since last session

Upcoming Plan (4 weeks)
    Wk  Date        Type  Grip      Sets (reps@kg x sets)   Rest  Total  TM
--  --  ----------  ----  --------  ----------------------  ----  -----  --
 >   1  2026-02-06  H     pronated  5x(6@+0.0)               120      30   9
     1  2026-02-09  E     pronated  (4,3,3,3,3,3,3,3)@+0.0    60      28   9
     ...
     4  2026-03-03  S     pronated  4x(5@+2.5)               240      20  10
```

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

| Type | Description | Reps | Rest |
|------|-------------|------|------|
| S | Strength | 3-6 | 180-300s |
| H | Hypertrophy | 6-12 | 120-180s |
| E | Endurance/Density | 3-8 | 45-90s |
| T | Technique | 2-4 | 60-120s |
| TEST | Max test | max | 180s |

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
│       ├── main.py        # Typer CLI
│       └── views.py       # Rich formatting
└── tests/
    └── test_cli_smoke.py  # Smoke tests
```

## License

This software is licensed under CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 International).

- **Commercial use is not permitted.**
- **Non-commercial use requires attribution** with a direct link to the original repository.

See [LICENSE](LICENSE) for full terms.
