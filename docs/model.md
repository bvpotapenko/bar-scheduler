# Training Model Reference

The complete math and rules behind plan generation, fatigue accounting, and max
estimation — with the module that owns each piece and the config knob that tunes it.

This is the single source of truth for the model. It supersedes the old
`formulas_reference`, `core_training_formulas_fatigue`, `training_model`,
`1rm_formulas`, `max_estimation`, `performance-formulas`, and `adaptation_guide`
documents (all merged here).

---

## Where each behavior lives (targetability map)

Every behavioral rule is one injectable, unit-tested component. To change a
behavior, edit only the listed module (and its test).

| To change… | Edit |
|---|---|
| rest / bodyweight / grip normalization | `core/math/normalization.py` |
| 1RM formulas + rep-range blend | `core/math/formulas.py` |
| effective-load (Leff) 1RM from history | `core/math/leff.py` |
| between-test "fresh max" (Track B) | `core/math/nuzzo.py`, `core/policies/max_estimation.py` |
| per-session training-load impulse `w(t)` | `core/math/training_load.py` |
| fitness / fatigue / readiness | `core/policies/fatigue.py` |
| weight & assistance prescribed | `core/policies/load.py` |
| sets / reps / intra-session decay | `core/policies/sets.py` |
| rest interval prescribed | `core/policies/rest.py` |
| within-plan autoregulation | `core/policies/autoregulation.py` |
| TM progression toward goal | `core/policies/progression.py` |
| plateau call + deload triggers | `core/policies/plateau.py` |
| grip rotation | `core/policies/grip.py` |
| calendar + TEST placement | `core/policies/schedule.py`, `core/policies/test_inserter.py` |
| overtraining severity | `core/services/overtraining.py` |
| plan orchestration (no rules) | `core/services/planning_service.py` |
| typed config defaults | `config/{model_params,planning_params,schedule_params}.py` |

`PlanningService` holds **no domain rules** — it sequences the policies via
`PrescriptionContext` / `AdaptationSignals` value objects (`domain/context.py`).
Config flows in once via the `dependency_injector` container (`containers.py`).

---

## Notation

| Symbol | Meaning |
|---|---|
| `reps` | reps completed in a set |
| `Leff` | effective load (kg) = `BW × bw_fraction + added_weight − assistance` |
| `TM` | training max (reps) — the plan's working anchor |
| `M_hat` | EWMA-smoothed estimate of current standardized max reps |
| `G(t), H(t)` | fitness, fatigue impulse-response state |
| `R(t)` | readiness = `G(t) − H(t)`; `z` = standardized readiness |
| `w(t)` | per-session training-load impulse |

---

## 1. Normalization (`core/math/normalization.py`)

Normalization makes sessions with different rest, load, grip, and bodyweight
comparable.

**Rest** — `rest_factor`
```
F_rest(r) = clip( (max(r, REST_MIN_CLAMP) / REST_REF_SECONDS) ^ GAMMA_REST,
                  F_REST_MIN, F_REST_MAX )
effective_reps = reps / F_rest(r)      # short rest -> F<1 -> more credit
```

**Bodyweight** — `bodyweight_normalized_reps` (always **linear**; there is no
`GAMMA_BW`)
```
reps_bw = reps × Leff / BW_ref          # BW_ref = reference (latest) bodyweight
```

**Grip / variant** — `grip_factor`
```
F_grip = variant_factors[grip]          # from ExerciseDefinition; 1.0 if unknown
```

**Combined** — `standardized_reps = effective_reps × (Leff / BW_ref) × F_grip`.

| Knob | Default | Effect |
|---|---|---|
| `REST_REF_SECONDS` | 180 | `F_rest = 1.0` at this rest |
| `GAMMA_REST` | 0.2 | steeper → short rest penalised more |
| `F_REST_MIN` / `F_REST_MAX` | 0.8 / 1.05 | floor / ceiling on the rest factor |
| `REST_MIN_CLAMP` | 30 | rest below this is treated as 30 s |

---

## 2. Session performance metrics

| Metric | Module | Formula |
|---|---|---|
| `session_max_reps` | `math/history_queries.py` | `max(actual_reps)` over BW-only sets (weighted sets excluded; 0 if none) |
| `latest_test_max` | `math/history_queries.py` | `session_max_reps` of the most recent TEST |
| `compliance_ratio` | `math/compliance.py` | `Σ actual_reps / Σ target_reps`; `weekly_compliance` averages over a window |
| `trend_slope_per_week` | `math/trend.py` | OLS slope of `(day, session_max_reps)` over TEST sessions in the last `TREND_WINDOW_DAYS`, in reps/week |

---

## 3. Training max (`core/math/training_max.py`)

```
training_max               = max(1, floor(TM_FACTOR × latest_test_max))
training_max_from_baseline = max(1, floor(TM_FACTOR × baseline_max))
```

`TM_FACTOR = 0.9`. `get_training_status` reports `training_max =
floor(0.9 × test_max)` (the conventional definition). The plan's **starting** TM
is the baseline/test-derived value above, and it grows upward from there
(§10) rather than spending weeks catching back up to proven performance.

---

## 4. 1RM estimation (`core/math/formulas.py`, `leff.py`)

Total 1RM is estimated in **Leff units** with a rep-range-aware blend — Epley
alone over-estimates beyond ~10 reps, so different ranges average different
published formulas (`best_onerm_from_leff`):

```
r <= 5   -> avg(Brzycki, Lander)
r <= 10  -> avg(Brzycki, Lander, Epley)
r > 10   -> avg(Lombardi, Epley)
```

| Formula | Definition |
|---|---|
| Epley | `w × (1 + reps/30)` |
| Brzycki | `w / (1.0278 − 0.0278 × reps)` |
| Lander | `100 × w / (101.3 − 2.67123 × reps)` |
| Lombardi | `w × reps^0.1` |

`blended_onerm_added(bw_load, reps)` returns the **added** kg only
(`total − bw_load`), and is `None` past 20 reps (estimate no longer reliable).

**From history** (`leff.py`): for every recorded set,
`Leff = BW × bw_fraction + added_weight − assistance`, and
`estimate_effective_leff_onerm` takes the **max** `best_onerm_from_leff(Leff, reps)`
across all sets. `resolve_leff_onerm` blends that history estimate with a
TM-derived fallback (history wins when above a floor).

The public 1RM endpoint (`get_onerepmax_data`) shows Epley, Brzycki, Lander,
Lombardi, Blended, and the recommended formula for the rep range.

---

## 5. Between-test "fresh max" — Track B (`core/math/nuzzo.py`, `policies/max_estimation.py`)

Track B estimates a fresh single-set max from an ordinary multi-set session
(no dedicated test), shown per past session as `track_b`.

**Fatigue index** (Pekünlü & Atalağ 2013):
```
FI = clip( 1 − mean(R2..Rn) / R1, 0, 1 )
```

**FI method** — correct set-1 reps for incomplete PCr recovery (Bogdanis 1995)
and scale up when fresh:
```
pcr      = max( interp(PCR_RECOVERY, rest_before_first), 0.5 )
fi_adj   = max(0, 0.35 − FI) × 0.6
fi_est   = round( (R1 / pcr) × (1 + fi_adj) )
```

**Nuzzo method** (2024) — invert a reps~%1RM regression table:
```
reps_to_failure = R1 + rir1            # rir1 inferred from FI when unreported
nuzzo_est       = round( reps_to_failure / %1RM(reps_to_failure) )
```

`MaxEstimator.estimate` returns `MaxEstimate(fi_est, nuzzo_est, fi_reps,
confidence)`; `None` if fewer than 2 sets had reps. Confidence is `high`
(≥4 sets + RIR known), `medium` (≥2 sets), else `low`.

---

## 6. Effort & training load (`core/math/effort.py`, `training_load.py`)

**RIR estimate** (when unreported): `estimate_rir_from_fraction = clip(M_hat − reps, 0, 5)`.

**RIR effort multiplier** — near-failure work costs more, and easy (high-RIR)
work costs **less than neutral** (sub-1.0):
```
E_rir(rir) = max( 0.5, 1 + A_RIR × (3 − rir) )
```
RIR 0 → ×1.45 · RIR 3 → ×1.0 · RIR 4 → ×0.85 · RIR ≥5 → floored at 0.5.

**Per-session impulse** `w(t)`:
```
hard_reps_j = actual_reps_j × E_rir(rir_j)
S_load_j    = (Leff_j / BW_ref) ^ GAMMA_LOAD
w(t)        = Σ_j  hard_reps_j × S_load_j × F_grip(grip)
```
**Rest stress is deliberately excluded** from `w(t)`: short rest is already
credited through rest-normalized effective reps, so charging it again here would
double-count fatigue.

| Knob | Default | Effect |
|---|---|---|
| `A_RIR` | 0.15 | per-RIR-below-3 effort bonus |
| `GAMMA_LOAD` | 1.5 | superlinear — added weight stresses the system more than proportionally |

---

## 7. Fitness–fatigue & readiness (`core/policies/fatigue.py`)

Two-timescale Banister impulse response, advanced session by session
(rest days decay both states):
```
G(t) = G(t-1) · e^(−d/TAU_FITNESS) + K_FITNESS · w(t)     # fitness (slow)
H(t) = H(t-1) · e^(−d/TAU_FATIGUE) + K_FATIGUE · w(t)     # fatigue (fast)
R(t) = G(t) − H(t)                                         # readiness
z    = (R − readiness_mean) / sqrt(readiness_var)
```
`readiness_mean` / `readiness_var` track `R` via EWMA (α = 0.1). On a TEST
session the observed max updates the EWMA max estimate:
```
M_hat  = (1 − ALPHA_MHAT)·M_hat + ALPHA_MHAT·M_obs
sigma² = (1 − BETA_SIGMA)·sigma² + BETA_SIGMA·(M_obs − M_hat)²
```

**Readiness-adjusted max** (`predicted_max`):
```
M_pred = M_base × (1 + C_READINESS × (R − R_bar))
```

| Knob | Default | Effect |
|---|---|---|
| `TAU_FITNESS` / `TAU_FATIGUE` | 42 / 7 days | fitness lingers; fatigue clears in ~1–2 weeks |
| `K_FITNESS` / `K_FATIGUE` | 0.5 / 1.0 | fatigue > fitness gain → readiness dips after hard work |
| `ALPHA_MHAT` / `BETA_SIGMA` | 0.25 / 0.15 | how fast `M_hat` / uncertainty track new tests |
| `C_READINESS` | 0.02 | scale of daily readiness swing on predicted max |

---

## 8. Set & rep prescription (`core/policies/sets.py`)

**Target reps** — mid-range from TM and the session params, clamped to
`[reps_min, reps_max]`:
```
target = clip( (max(reps_min, TM·frac_low) + min(reps_max, TM·frac_high)) // 2,
               reps_min, reps_max )
```
TEST target = `round(TM / TM_FACTOR) + 1` (one rep above last result), or
`reps_max` with no prior test.

**Level classification** — the latest test max maps to a discrete level against
the exercise's `level_thresholds` (first threshold ≥ test max; middle level when
unknown). `sets_by_level[level]` gives the base set count (else the mid of
`sets_min..sets_max`).

| Exercise | `level_thresholds` | L0 / L1 / L2 / L3 |
|---|---|---|
| Pull-Up | `[4, 13, 24]` | ≤4 / 5–13 / 14–24 / ≥25 |
| Dip | `[7, 19, 33]` | ≤7 / 8–19 / 20–33 / ≥34 |
| BSS | `[5, 12, 20]` | ≤5 / 6–12 / 13–20 / ≥21 |
| Incline DB Press | `[4, 9, 14]` | ≤4 / 5–9 / 10–14 / ≥15 |

**Intra-session rep decay** — for S/H/T/TEST, each set's reps are scaled by the
exercise's `set_fatigue_curve` (empirical set-to-set drop-off; last factor reused
past its length):
```
target_reps[i] = max(1, round(adj_reps × curve[i]))
```
Default pull/dip/press curve `[1.0, 0.85, 0.75, 0.68, 0.63]`; BSS
`[1.0, 0.90, 0.82, 0.76, 0.72]`. **Endurance (E)** ignores the curve and uses a
descending rep ladder floored at `reps_min`. TEST is always 1 set.

---

## 9. Weight & assistance prescription (`core/policies/load.py`)

When `TM > weight_tm_threshold`, external load is added by inverting the Leff
1RM for the session's target reps:
```
leff_target = leff_onerm × TM_FACTOR / (1 + target_reps / 30)
added_kg    = clip( leff_target − BW × bw_fraction, 0, max_added_weight_kg )   # snapped to 0.5 kg / available weights
assistance  = ceil_snap( BW × bw_fraction − leff_target )                       # when below threshold & bands/machine declared
```
Target reps per session type (drives the inverse): **S 5 · H 8 · E 12 · T 6 ·
TEST 1** (≈85 / 78 / 67 / 83 / max %1RM). Below the threshold `added_kg = 0`
(bodyweight-only phase). `external_only` exercises (incline DB press) carry the
last TEST weight forward when no history-derived estimate exists.

Discrete equipment: declared weights **floor-snap** (largest ≤ ideal); machine /
band assistance **ceiling-snaps** (smallest ≥ needed). As TM grows the planner
automatically reduces assistance, then begins adding weight.

---

## 10. Rest, autoregulation, progression

**Rest** (`policies/rest.py`) — start at the session midpoint
`(rest_min + rest_max)//2`, then adjust by recent same-type signals and clamp to
`[rest_min, rest_max]`:

| Signal | Δ rest |
|---|---|
| any set near failure (RIR ≤ 1) | +30 s |
| all sets felt easy (RIR ≥ 3) | −15 s |
| within-session rep drop-off > `DROP_OFF_THRESHOLD` (0.35) | +15 s |
| readiness `z < READINESS_Z_LOW` | +30 s |
| user's actual rest consistently short / long (≥3 points) | −20 / +20 s |

**Autoregulation** (`policies/autoregulation.py`) — applied once history has
`≥ MIN_SESSIONS_FOR_AUTOREG` (3) sessions:
```
z < READINESS_Z_LOW (−0.5):   sets = max(sets_min, floor(base_sets × (1 − READINESS_VOLUME_REDUCTION)))
z > READINESS_Z_HIGH (+0.5):  reps = base_reps + 1
else:                         unchanged
```

**Progression** (`policies/progression.py`) — weekly TM gain decelerates toward
the goal:
```
reps_per_week = DELTA_PROGRESSION_MIN
              + (DELTA_PROGRESSION_MAX − DELTA_PROGRESSION_MIN) × (1 − TM/target)^ETA_PROGRESSION
```
Reps-only goals stop TM at the goal reps. Weighted goals keep TM growing
(≥ `DELTA_PROGRESSION_MIN`/week) until both the rep target and the projected
added weight at goal reps are met.

| Knob | Default |
|---|---|
| `TARGET_MAX_REPS` | 30 |
| `DELTA_PROGRESSION_MIN` / `MAX` | 0.3 / 1.0 reps/week |
| `ETA_PROGRESSION` | 1.5 |

Example: TM 5 → ~0.97 · TM 15 → ~0.68 · TM 25 → ~0.36 · TM 29 → ~0.30 reps/week.

---

## 11. Plateau & deload (`core/policies/plateau.py`)

**Plateau** = flat trend **and** no new best within the window:
```
plateaued = (trend_slope_per_week < PLATEAU_SLOPE_THRESHOLD)
            AND no TEST in the last PLATEAU_WINDOW_DAYS matched/beat the all-time best
            (requires ≥ 2 TEST sessions)
```

**Deload** fires if **any** hold:
```
1. plateaued AND readiness z < FATIGUE_Z_THRESHOLD
2. last 2 S-sessions all below M_pred × (1 − UNDERPERFORMANCE_THRESHOLD)
3. weekly_compliance(1 week) < COMPLIANCE_THRESHOLD
```
`fatigue_score = (latest_test_max − M_pred) / M_pred` (<0 = underperforming).

| Knob | Default |
|---|---|
| `PLATEAU_SLOPE_THRESHOLD` | 0.05 reps/week |
| `PLATEAU_WINDOW_DAYS` / `TREND_WINDOW_DAYS` | 21 / 21 days |
| `FATIGUE_Z_THRESHOLD` | −0.5 |
| `UNDERPERFORMANCE_THRESHOLD` | 0.10 |
| `COMPLIANCE_THRESHOLD` | 0.70 |

---

## 12. Overtraining severity (`core/services/overtraining.py`)

Compares how compressed the last 7 days are against the planned frequency
(unlogged days count as rest):
```
expected_span  = (sessions − 1) × (7 / days_per_week)
extra_rest     = max(0, round(expected_span − actual_span_days))
level          = 0 if extra==0 ; 1 if ==1 ; 2 if <=3 ; else 3
```
Needs ≥ 2 sessions in the window; otherwise level 0. Exposed via
`get_overtraining_status` and `get_plan()["overtraining"]`; at level ≥ 2 the
plan start is shifted forward.

---

## 13. Plan generation (`core/services/`)

`PlanningService.generate(PlanRequest)` sequences the policies:

1. **Setup** (`plan_setup.RunFactory`) — build a `PlanRun`: history window,
   effective initial TM (`training_max` / baseline), training state
   (`training_state.TrainingStateCalculator`), goal, calendar slots, grip
   selector.
2. **Calendar** (`plan_calendar.PlanCalendar` → `schedule.ScheduleBuilder` +
   `test_inserter.TestSessionInserter`) — lay out session days from the weekly
   template and insert TEST sessions when due.
3. **Weekly TM fold** — iterate slots; when the session's week index advances,
   add `progression.weekly_delta(...)` once.
4. **Prescribe** (`slot_prescriber.Prescriber` → `SetPrescriptor` + `LoadCalculator`)
   — build each `SessionPlan` from the current TM.

**Weekly template / schedule:**

| days/week | template | spacing |
|---|---|---|
| 1 | `S` | — |
| 2 | `S H` | |
| 3 | `S H E` | |
| 4 | `S H T E` | 4-day offsets `[0,2,4,5]` (Mon/Wed/Fri/Sat) keep a 48 h S→H gap |
| 5 | `S H T E S` | |

`DAY_SPACING["TEST"] = 1` → the session after a TEST is placed ≥ TEST_date + 2.
Week numbers are cumulative, anchored to the first session in history.

**Prescription stability invariant:** `prescription(D) = f(history dated < D,
profile)` — a plan for date D depends only on history before D, so re-generating
never rewrites the past.

---

## 14. Config constants (`config/`)

Typed OmegaConf-structured dataclasses; defaults below. Override any key in
`~/.bar-scheduler/exercises.yaml` (deep-merged over the bundled
`src/bar_scheduler/exercises.yaml`).

| Section (`config/…`) | Keys |
|---|---|
| `model_params.RestNormalizationConfig` | `REST_REF_SECONDS=180`, `GAMMA_REST=0.2`, `F_REST_MIN=0.8`, `F_REST_MAX=1.05`, `REST_MIN_CLAMP=30` |
| `model_params.EwmaMaxConfig` | `ALPHA_MHAT=0.25`, `BETA_SIGMA=0.15`, `INITIAL_SIGMA_M=1.5` |
| `model_params.FitnessFatigueConfig` | `TAU_FATIGUE=7`, `TAU_FITNESS=42`, `K_FATIGUE=1.0`, `K_FITNESS=0.5`, `C_READINESS=0.02` |
| `model_params.TrainingLoadConfig` | `A_RIR=0.15`, `GAMMA_LOAD=1.5` |
| `planning_params.VolumeConfig` | `WEEKLY_HARD_SETS_MIN=8`, `MAX=20`, `MAX_DAILY_REPS=45`, `MAX_DAILY_SETS=10` |
| `planning_params.ProgressionConfig` | `TM_FACTOR=0.9`, `TARGET_MAX_REPS=30`, `DELTA_PROGRESSION_MIN=0.3`, `MAX=1.0`, `ETA_PROGRESSION=1.5` |
| `planning_params.PlateauConfig` | `PLATEAU_SLOPE_THRESHOLD=0.05`, `PLATEAU_WINDOW_DAYS=21`, `TREND_WINDOW_DAYS=21`, `FATIGUE_Z_THRESHOLD=-0.5`, `UNDERPERFORMANCE_THRESHOLD=0.1`, `COMPLIANCE_THRESHOLD=0.7` |
| `planning_params.AutoregulationConfig` | `MIN_SESSIONS_FOR_AUTOREG=3` |
| `planning_params.ReadinessConfig` | `READINESS_Z_LOW=-0.5`, `READINESS_Z_HIGH=0.5`, `READINESS_VOLUME_REDUCTION=0.3` |
| `schedule_params.PlanHorizonConfig` | `MIN_PLAN_WEEKS=2`, `MAX_PLAN_WEEKS=52`, `DEFAULT_PLAN_WEEKS=4` |
| `schedule_params.ScheduleConfig` | `SCHEDULE_{1..5}_DAYS`, `DAY_SPACING={S:1,H:1,E:1,T:0,TEST:1}` |

`weight_tm_threshold`, `max_added_weight_kg`, `level_thresholds`,
`set_fatigue_curve`, `variant_factors`, and `session_params` are **per-exercise**
(in each exercise YAML; see [exercise-structure.md](exercise-structure.md)).

---

## References

- Banister fitness-fatigue impulse response (two-timescale model)
- Epley / Brzycki / Lander / Lombardi 1RM regressions
- Nuzzo et al. 2024 — reps~%1RM bench-press regression
- Pekünlü & Atalağ 2013 — fatigue-index max estimation
- Bogdanis et al. 1995 — PCr resynthesis after maximal exercise
- Strength Level database (4.8M+ lifts) — level thresholds
