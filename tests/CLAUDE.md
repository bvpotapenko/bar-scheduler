# tests/ — test suite

## Two tiers

| Location | Type | Tests |
|----------|------|-------|
| `test_api.py` | Unit | All public API functions; error handling; edge cases |
| `test_planner_logic.py` | Unit | Low-level planner: load calc, set prescription, grip rotation, rest |
| `golden/` | Integration | End-to-end: init → plan → test sessions → volume → simulation |

## Golden tests

The golden tests freeze expected outputs as constants. They catch systemic regressions that unit tests miss.

- **Layer structure:** layer1=init, layer2=plan, layer3=test session insertion, layer4=volume adaptation, layer5=long-horizon simulation
- **Constants files** (`constants_p1/2/3.py`) are generated, not hand-written. If an intentional model change shifts expected values, run: `python tests/golden/regenerate.py`
- **Never hand-edit constants.** If a golden test fails and the new behavior is correct, regenerate.
- **conftest.py** provides 3 test profiles (p1/p2/p3) with pre-built training histories. Use these fixtures in golden tests; don't create fresh profiles inside golden test functions.
- **history_data.py** is the mock training history. Edit it only when new session types or fields are needed for coverage.

## Where to add new tests

- New API function → `test_api.py`
- New planner logic → `test_planner_logic.py`
- Systemic behavior change (e.g. new session type affects plan structure) → golden layer test
- Every test must assert at least one specific expected value (see root CLAUDE.md testing rules)
