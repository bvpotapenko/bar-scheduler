# bar-scheduler

Evidence-informed training planner for bodyweight and weighted strength exercises -- **Pull-Up**, **Parallel Bar Dip**, **Bulgarian Split Squat (DB)** - can be extended to more via YAML config.


A Python library and planning engine. Suitable for direct use in scripts, bots, and web services. 

For an interactive command-line interface see [cli_bar](https://github.com/bvpotapenko/cli_bar). 

There is an aplpha in progres for a telegram bot -- stay tuned, more details on my telegram channel: [@RoboRice](https://t.me/roborice)!


> **From the author:**
>
> I started this project to motivate myself to do pull-ups more consistently. I also wanted to try a more “science-backed” approach and see whether it actually delivers results.
>
> What began with pull-ups quickly grew into a broader routine -- I added dips and Bulgarian split squats, and now I’m considering incline dumbbell presses since I recently got a bench and a set of dumbbells.
>
> I hope this small project can inspire others to get in better shape and make steady progress toward their strength and physique goals.
>
> If you’d like to contribute or fork the project -- feel free. Have fun.


## Install

```bash
git clone <repo-url> && cd bar-scheduler
uv sync
```

```python
from pathlib import Path
from bar_scheduler.api.api import init_profile, get_plan, log_session, get_data_dir

data_dir = get_data_dir()   # ~/.bar-scheduler
                            # or Path("...") / str(user_id) for multi-user setups
```

## Documentation

| Document | Contents |
|---|---|
| [Python API](docs/api_info.md) | All public functions, signatures, and return-value shapes |
| [Features](docs/features.md) | Complete feature inventory |
| [Training Model](docs/training_model.md) | Adaptation and periodisation logic |
| [Formula Reference](docs/formulas_reference.md) | All formulas with config knobs |
| [Exercise Structure](docs/exercise-structure.md) | How to add a custom exercise |
| [Plan Logic](docs/plan_logic.md) | Prescription stability invariant, plan anchor mechanics |
| [Adaptation Guide](docs/adaptation_guide.md) | What to expect at each training stage |
| [References](REFERENCES.md) | The scientific publications and evidence-based sources used to design the training formulas, fatigue model, and progression rules in the planner core engine. |

## Running Tests

```bash
uv sync --extra dev
uv run pytest
```

## License

CC BY-NC 4.0 -- non-commercial use with attribution. See [LICENSE](LICENSE).

Author: Potapenko Bogdan  
*ML / AI Engineer @ Shenzhen, 2026*     
Telegram: https://t.me/roborice
