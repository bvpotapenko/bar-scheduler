# core/ — computation layer

## Module map

| Module | Owns |
|--------|------|
| `metrics.py` | All pure math: rest normalization, effective reps, bodyweight scaling, RIR estimation |
| `physiology.py` | Fitness-fatigue impulse response model; readiness; predicted max with fatigue |
| `adaptation.py` | Plateau detection, deload triggers, overtraining severity, readiness assessment |
| `equipment.py` | Leff calculation, band/machine assistance lookup, assistance progression |
| `max_estimator.py` | 1RM estimation from test sessions; EWMA smoothing; variant normalization |
| `models.py` | All dataclasses — the shared data model for the entire library |
| `config.py` | Constants (TAU_FITNESS, PLATEAU_WINDOW_DAYS, etc.) loaded from YAML at import |
| `timeline.py` | Merges past history + future plan into a unified timeline; computes week numbers |
| `planner/` | Plan generation — see planner/CLAUDE.md |
| `exercises/` | Exercise definitions loaded from YAML; global registry |
| `engine/config_loader.py` | Loads exercises.yaml (bundled + optional user override) |

## Dependency order

```
metrics.py  ←  physiology.py  ←  adaptation.py
     ↑               ↑
equipment.py    max_estimator.py
     ↑
  planner/
```

`metrics.py` is the root. Everything downstream depends on it. Never introduce a reverse dependency (e.g. metrics importing from physiology).

## Key invariants

- **Pure and stateless.** All modules are side-effect-free — no I/O, no disk, no global state mutation. `exercises/registry.py` is the only exception: it caches loaded definitions once at import time.
- **models.py is the lingua franca.** Cross-module calls pass dataclasses, not raw dicts. No ad-hoc dicts between core modules.
- **config.py is constants only.** Never put logic in config.py; it's a flat bag of named values.

## When to edit what

- **metrics.py** — changing how effort, rest, or bodyweight are computed; formula corrections
- **physiology.py** — fitness-fatigue model coefficients or structure; RIR effort multiplier
- **adaptation.py** — plateau/readiness heuristics; deload threshold tuning
- **equipment.py** — Leff formula; assistance catalog; band/machine progression logic
- **config.py** — constant value changes only (not new logic)

## Reference docs

- `docs/training_model.md` — physiology formulas
- `docs/adaptation_guide.md` — plateau and readiness heuristics
- `docs/formulas_reference.md` — all math symbols and formulas
- `docs/1rm_formulas.md`, `docs/max_estimation.md` — max estimation
