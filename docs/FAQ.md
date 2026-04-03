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

Session target reps: S -> 5, H -> 8, E -> 12, T -> 6 (corresponding to ~85/78/67/83 % of 1RM).

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

## How do I read a load number — what does "load = 19" mean?

**Load is a personal, relative measure** — not absolute work. The same sets and reps produce different load values for different people because everything is normalized to *your* bodyweight and estimated from *your* current max. Two people doing identical pull-ups will have different loads. You can only meaningfully compare your own load numbers over time.

**The unit anchor: load = 1 ≈ one comfortable pull-up at your bodyweight** (RIR ~3, no band assistance, no added weight). Session load is the sum over all sets.

Two things amplify load beyond the raw rep count:

- **Effort (RIR).** Reps close to failure count more. RIR 0 (nothing left) multiplies load per rep by ×1.45; RIR 5+ (very easy) multiplies by ×0.70. Same reps, very different load — effort compresses or expands the signal.
- **Added weight (super-linear).** Load scales as `(Leff / BW)^1.5`. Adding 20 kg at 80 kg bodyweight raises effective load by 25% but raises load contribution per rep by ~40%. Heavier weight punishes more than proportionally.

**Is "load = 100" the same as 100 pull-ups?**

No. A single hard set of 10 reps near failure produces more load than 10 easy sets of 1 rep, even though the rep total is identical. Load measures how much of *your* capacity was deployed, not how many reps were logged.

**Load scale reference (pull-ups at bodyweight, no added weight):**

| Session load | What it looks like |
|--------------|--------------------|
| ~15–20 | Light session — 3 sets × 5 reps, moderate effort |
| ~40–50 | Solid training session — 4–5 sets × 8–10 reps |
| ~80+ | Very hard session — near-failure sets or significant added weight |

### Theoretical maximums

**Single max-effort set ceiling:**

```
≈ test_max × 1.45
```

One all-out set to absolute failure (RIR 0) at bodyweight. For someone with `test_max = 15`, this is ~22 load.

**Multi-set ceiling (grind until you can't lift):**

```
≈ test_max × 8–10
```

Reps decay per set following an exponential model (λ ≈ 0.08 per set), so total rep volume converges to roughly `test_max × 13`. With realistic short rest (~60 s) and an average effort multiplier of ~0.85 across all sets (high on early sets, lower once per-set reps drop), the ceiling is approximately `test_max × 8–10`.

For `test_max = 15`: ceiling ≈ 120–150. Nobody trains there — it would take days to recover — but a well-programmed session sits at roughly **20–35% of that ceiling**. That gap is your long-term growth room.

---

## Why do later sets in my session have fewer reps than set 1?

This is intentional. The planner applies a **per-set rep decay curve** (`set_fatigue_curve`) based on empirical data showing that rep performance drops roughly 15–30% from set 1 to set 2, then continues to decline with each additional set (PMC11057609). Rather than prescribing a uniform rep target that you'll fail to hit on the last set, the plan models the expected decay:

| Set | Pull-up factor | Example (7 reps on set 1) |
|-----|---------------|--------------------------|
| 1 | 1.00 | 7 reps |
| 2 | 0.85 | 6 reps |
| 3 | 0.75 | 5 reps |
| 4 | 0.68 | 5 reps |
| 5 | 0.63 | 4 reps |

Set 1 is your benchmark for the session. If you hit set 1 reps comfortably, the later sets should also feel manageable. If set 2 is already a grind, take more rest or reduce load.

The decay curves differ by exercise: lower-body exercises (BSS) decay more slowly than upper-body pulling/pushing movements.

E (endurance) sessions have their own descending rep ladder and are not affected by this curve. TEST sessions are always 1 set.

---

## How does the planner decide how many sets to prescribe?

Sets are determined by your **training level**, derived from your latest TEST session max-reps. Level thresholds are calibrated from the Strength Level database (4.8M+ lifts):

| Exercise | Levels | Thresholds |
|----------|--------|------------|
| Pull-Up | 0–3 | ≤4 / 5–13 / 14–24 / ≥25 reps |
| Dip | 0–3 | ≤7 / 8–19 / 20–33 / ≥34 reps |
| BSS | 0–3 | ≤5 / 6–12 / 13–20 / ≥21 reps/leg |
| Incline DB Press | 0–3 | ≤4 / 5–9 / 10–14 / ≥15 reps |

Each session type has a `sets_by_level` table. Example for pull-up H (hypertrophy) sessions:

| Your level | H sets prescribed |
|-----------|-------------------|
| 0 (novice, ≤4 reps) | 2 |
| 1 (beginner, 5–13 reps) | 3 |
| 2 (intermediate, 14–24 reps) | 4 |
| 3 (advanced, ≥25 reps) | 5 |

Before your first TEST session, the planner defaults to the middle level (1). After your first TEST, the level is recalculated from your result and sets adjust from the next session onward.

If your readiness is very low (fitness-fatigue z-score < −1.0) and autoregulation is active (≥10 sessions logged), the planner may reduce sets by up to 30% but will never go below `sets_min` (1 set by default).

---

## What is the fitness-fatigue model?

The planner tracks two exponential signals to estimate readiness:

- **Fitness** (G): decays slowly (`TAU_FITNESS = 42 days`); reflects long-term adaptation.
- **Fatigue** (H): decays quickly (`TAU_FATIGUE = 7 days`); reflects acute recovery need.
- **Readiness** = G − H.

Both signals are updated after every session using the training load `w(t)`. The readiness z-score gates autoregulation and can trigger volume reductions.
