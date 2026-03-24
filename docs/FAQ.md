# bar-scheduler FAQ

Answers to "how does it work?" questions about the active planning engine.

---

## What are session types and what do they train?

Each training week rotates through up to four session types, each targeting a different rep range and physiological adaptation:

| Type | Name | Rep range | Purpose |
|------|------|-----------|---------|
| S | Strength | ~4–6 reps | Peak force output; heaviest load |
| H | Hypertrophy | ~6–12 reps | Muscle growth; moderate load and volume |
| E | Endurance | descending ladder | Muscular endurance; high total reps, low rest |
| T | Technique | ~5–8 reps | Movement quality; sub-maximal, no fatigue target |

Session type also controls how the planner prescribes weight (see "How does weight prescription work?" below).

---

## How does the planner adapt rest between sets?

Rest is prescribed per-session-type from a range defined in the exercise YAML (e.g. `rest_min`/`rest_max` for S sessions). The planner adapts the value based on readiness:

- **Low readiness** (fitness-fatigue z-score below threshold): rest increases toward `rest_max`.
- **High readiness**: rest decreases toward `rest_min`.
- **No history**: the midpoint `(rest_min + rest_max) // 2` is used.

Rest adaptation activates only after ≥ 10 sessions are logged (`MIN_SESSIONS_FOR_AUTOREG`).

---

## How does weight prescription work?

The planner uses the Epley 1RM inverse formula to determine how much external weight to add per session:

1. **Estimate Leff 1RM** from all historical sets: `1RM_Leff = Leff × (1 + reps / 30)` where `Leff = BW × bw_fraction + added − assistance`.
2. **Invert for the session's target reps**: `Leff_target = 1RM_Leff × TM_FACTOR / (1 + target_reps / 30)`.
3. **Derive added weight**: `added = max(0, Leff_target − BW × bw_fraction)`, rounded to 0.5 kg, capped at the exercise maximum.

Session target reps: S → 5, H → 8, E → 12, T → 6 (corresponding to ~85/78/67/83 % of 1RM).

No weight is prescribed when `TM ≤ weight_tm_threshold` (the bodyweight-only phase).

---

## How does bodyweight normalization work?

All exercises use **linear effective load normalization**:

```
reps** = reps* × (Leff / Leff_ref)
```

where `Leff = BW × bw_fraction + added − assistance` and `Leff_ref` is the reference effective load (typically the session bodyweight). This scales reps proportionally to load — linear scaling is correct for all supported exercise types (pull-up, dip, BSS, and external-only).

---

## How do exercise goals work?

Goals are set with `set_exercise_target(data_dir, exercise_id, reps=N)` or `set_exercise_target(data_dir, exercise_id, reps=N, weight_kg=W)`.

**Reps-only goal** (`weight_kg=0`): the planner stops increasing the Training Max (TM) once `TM ≥ goal_reps`. Use this for "I want to do 20 pull-ups."

**Weighted goal** (`weight_kg>0`): the planner continues growing TM even after `TM ≥ goal_reps`, because reaching the weight target requires a higher 1RM. Progression stops only when both conditions are true:
- `TM ≥ goal_reps`
- The Epley-derived weight prescription at `goal_reps` ≥ `goal_weight_kg`

The Epley cycle naturally handles the rep drop-then-recover pattern that occurs when external weight is added. Use this for "I want 5 pull-ups with +20 kg."

If no goal is set, the planner uses the exercise's built-in target (e.g. 30 reps for pull-ups).

---

## How does TEST session recovery work?

After a TEST session (max-effort assessment), the planner enforces a minimum rest gap before the next training session:

- `DAY_SPACING["TEST"] = 1`: the next session must be at least 2 days after the TEST (1 rest day between).
- This applies to both historical TEST sessions (affects the first plan session) and TEST sessions inserted within the plan.

The value is configurable in `exercises.yaml` under `schedule.DAY_SPACING.TEST`.

---

## How often does the planner insert TEST sessions?

TEST sessions are inserted every `test_frequency_weeks` weeks (defined per exercise in its YAML file). They replace a regular training slot on the scheduled day. The TEST slot counts progress from the last TEST date, not from plan start.

---

## What is the Training Max (TM)?

The Training Max is the rep count the planner uses to calibrate all prescriptions:

```
TM = floor(TM_FACTOR × latest_test_max)
```

`TM_FACTOR = 0.90` by default, so TM starts at 90% of your assessed maximum. The plan then grows TM week-over-week at a rate given by `expected_reps_per_week(TM, target)`, which slows as you approach the target.

---

## What is training load and how is it calculated?

Training load (`w(t)`) quantifies the physiological stress of each session using the Banister impulse formula:

```
w(t) = Σ (actual_reps × E_rir × (Leff / BW_ref)^GAMMA_LOAD × S_variant)
```

Where:
- `E_rir`: effort multiplier based on Reps In Reserve (RIR < 3 = harder than neutral)
- `Leff / BW_ref`: relative effective load (linear bodyweight normalization)
- `GAMMA_LOAD = 1.5`: load exponent
- `S_variant`: per-grip/variant stress factor from the exercise YAML

Use `get_load_data(data_dir, exercise_id)` to retrieve historical and projected load values.

---

## What is the fitness-fatigue model?

The planner tracks two exponential signals to estimate readiness:

- **Fitness** (G): decays slowly (`TAU_FITNESS = 42 days`); reflects long-term adaptation.
- **Fatigue** (H): decays quickly (`TAU_FATIGUE = 7 days`); reflects acute recovery need.
- **Readiness** = G − H.

Both signals are updated after every session using the training load `w(t)`. The readiness z-score gates autoregulation and can trigger volume reductions.
