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

# View training plan
bar-scheduler plan

# Log a session
bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
    --grip pronated --session-type S --sets "5@0/180,5@0/180,4@0/180"

# View history
bar-scheduler show-history

# View progress chart
bar-scheduler plot-max
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize profile and history file |
| `plan` | Generate training plan |
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
- `8@0/180,6@0/120,5@0/120` - three sets

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

```
Current status
- Training max (TM): 9
- Latest test max: 10
- Trend (reps/week): +0.50
- Plateau: no
- Deload recommended: no

Upcoming Plan (2 weeks)
Date        Type  Grip      Sets (reps@kg x sets)    Rest(s)
----------  ----  --------  -----------------------  -------
2026-02-18  S     pronated  4x(4@+0.0)               240
2026-02-20  H     neutral   5x(8@+0.0)               150
2026-02-22  E     pronated  (7,6,5,5,4,4)@+0.0       60
```

### plot-max

```
Max Reps Progress (Strict Pull-ups)
──────────────────────────────────────────────────────────────
 30 ┤
 28 ┤
 26 ┤
 24 ┤
 22 ┤                                      ╭──● (23)
 20 ┤                                  ╭───╯
 18 ┤                              ╭───╯
 16 ┤                      ╭──● (16)
 14 ┤                  ╭───╯
 12 ┤          ╭──● (12)
 10 ┤      ╭───╯
  8 ● (8)──╯
  6 ┤
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

- [Training Model](docs/training_model.md) - formulas and adaptation logic
- [CLI Examples](docs/cli_examples.md) - CLI usage examples

## Project Structure

```
bar-scheduler/
├── pyproject.toml
├── README.md
├── docs/
│   ├── training_model.md
│   └── cli_examples.md
├── src/bar_scheduler/
│   ├── core/
│   │   ├── config.py      # All constants
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
