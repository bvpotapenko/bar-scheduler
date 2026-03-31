# planner/ — plan generation

## Orchestration

`plan_engine.py` is the orchestrator. The other modules are pure functions called in this sequence:

```
schedule_builder      → places session slots on calendar days
training_state        → computes TM, week number, history summary per session
load_calculator       → prescribes weights via Epley inverse + TM threshold
set_prescriptor       → assigns sets/reps per session type
grip_selector         → rotates variants (grip, stance) across sessions
rest_advisor          → recommends rest intervals
test_session_inserter → injects TEST sessions; may shift previously placed sessions
```

Each module is a pure function. Its output feeds the next step. None of them read from disk.

## Determinism invariant

`generate_plan(history, profile, date)` must always return the same output for identical inputs. This is load-bearing: the test suite and plan cache depend on it.

Rules that follow:
- No randomness, no `datetime.now()` inside planner modules (date is always passed in)
- New state must come from `history` or `profile` only — never from external sources
- Autoregulation reads from history; it does not introduce entropy

## Key constraints

- **test_session_inserter runs last.** It may shift sessions already placed in earlier steps. Never assume a session's final date before this step completes.
- **load_calculator.py owns the prescription formula** (Epley inverse, TM threshold, 0.0 below threshold). Do not replicate load math elsewhere.
- **Week numbers** are anchored to the first session in history; `plan_engine.py` delegates this to `timeline.py`.

## Adding a new plan feature

1. Create a new single-purpose module in `planner/`
2. Call it from `plan_engine.py` in the correct sequence position
3. Pass inputs as dataclasses (not dicts)
4. Add a unit test in `tests/test_planner_logic.py`
