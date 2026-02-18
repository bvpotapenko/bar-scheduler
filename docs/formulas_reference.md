# Formula Reference

All formulas used by the core engine, with the config.py knobs that control them.

---

## 1. Rest Normalization (`metrics.py`)

**rest_factor**
```
F_rest(r) = clip( (r / REST_REF_SECONDS)^GAMMA_REST, F_REST_MIN, F_REST_MAX )
```
| Parameter | Default | Effect |
|---|---|---|
| `REST_REF_SECONDS` | 180 | Reference rest; F_rest = 1.0 at this value |
| `GAMMA_REST` | 0.20 | Steeper → short rest penalised more |
| `F_REST_MIN` | 0.80 | Floor; even very short rest never drops below this |
| `F_REST_MAX` | 1.05 | Ceiling; very long rest adds at most 5% credit |
| `REST_MIN_CLAMP` | 30 | Any rest < 30 s is treated as 30 s before the formula |

**effective_reps** (rest-normalised reps)
```
reps* = reps / F_rest(rest)
```
Short rest → F_rest < 1 → reps* > reps (harder effort gets more credit).

---

## 2. Bodyweight Normalization (`metrics.py`)

**bodyweight_normalized_reps**
```
reps** = reps* * ((bw + load) / bw_ref)^GAMMA_BW
```
| Parameter | Default | Effect |
|---|---|---|
| `GAMMA_BW` | 1.0 | How strongly load ratio scales reps; 1.0 = linear |

`bw_ref` is the current (latest known) bodyweight of the user.

---

## 3. Grip Normalization (`metrics.py`)

**standardized_reps**
```
reps_std = reps** * F_grip
```
| Parameter | Default | Effect |
|---|---|---|
| `GRIP_FACTORS["pronated"]` | 1.00 | Standard reference grip |
| `GRIP_FACTORS["neutral"]` | 1.00 | Currently equal; raise to credit neutral as harder |
| `GRIP_FACTORS["supinated"]` | 1.00 | Currently equal; adjust if supinated differs meaningfully |

---

## 4. Session Performance Metrics (`metrics.py`)

**session_max_reps**
```
max(actual_reps) for sets where added_weight_kg == 0
```
Weighted sets are excluded; returns 0 if no BW-only sets.

**session_total_reps**
```
sum(actual_reps) across all completed sets
```

**drop_off_ratio**
```
D = 1 - mean(last_2_reps) / first_set_reps
```
| Parameter | Default | Effect |
|---|---|---|
| `DROP_OFF_THRESHOLD` | 0.35 | If D > this, session is flagged as high-fatigue |

---

## 5. Training Max (`metrics.py`)

**training_max**
```
TM = max(1, floor(TM_FACTOR * latest_test_max))
```
**training_max_from_baseline**
```
TM = max(1, floor(TM_FACTOR * baseline_max))
```
| Parameter | Default | Effect |
|---|---|---|
| `TM_FACTOR` | 0.90 | Conservative anchor; lower → more buffer below test max |

Note: the plan's starting TM uses `latest_test_max` directly (not `TM_FACTOR × test_max`) so the plan starts from proven performance and grows beyond it.

---

## 6. RIR Estimation (`metrics.py`)

**estimate_rir_from_fraction**
```
RIR_hat = clip(M_hat - reps, 0, 5)
```
Used when the athlete does not report RIR explicitly.

---

## 7. Within-Session Fatigue (`metrics.py`)

**predict_set_reps**
```
Q_rest(r)    = 1 - Q_REST_RECOVERY * e^(-r / TAU_REST_RECOVERY)
reps_pred[j] = floor( (p - RIR) * e^(-LAMBDA_DECAY*(j-1)) * Q_rest(rest_j) )
```
| Parameter | Default | Effect |
|---|---|---|
| `LAMBDA_DECAY` | 0.08 | Per-set rep decay within a session; higher → faster drop-off |
| `Q_REST_RECOVERY` | 0.30 | Max recovery possible from rest; higher → rest matters more |
| `TAU_REST_RECOVERY` | 60.0 s | Time constant for rest recovery; higher → need longer rest |

---

## 8. Trend Slope (`metrics.py`)

**trend_slope_per_week**
```
OLS linear regression on (day_index, session_max_reps) for TEST sessions
within the last TREND_WINDOW_DAYS days → slope converted to reps/week
```
| Parameter | Default | Effect |
|---|---|---|
| `TREND_WINDOW_DAYS` | 21 | Wider window → smoother, less reactive slope |

---

## 9. Compliance (`metrics.py`)

**compliance_ratio**
```
compliance = sum(actual_reps) / sum(target_reps)
```
`weekly_compliance` averages session compliance over the last `weeks_back` × 7 days.

---

## 10. RIR Effort Multiplier (`physiology.py`)

**rir_effort_multiplier**
```
E_rir(rir) = 1 + A_RIR * max(0, 3 - rir)
```
| Parameter | Default | Effect |
|---|---|---|
| `A_RIR` | 0.15 | Per-RIR-below-3 bonus; higher → near-failure sets contribute much more load |

RIR 3 → ×1.0 · RIR 2 → ×1.15 · RIR 1 → ×1.30 · RIR 0 → ×1.45

---

## 11. Rest Stress Multiplier (`physiology.py`)

**rest_stress_multiplier**
```
S_rest(r) = clip( (REST_REF_SECONDS / max(r, REST_MIN_CLAMP))^GAMMA_S, 1, S_REST_MAX )
```
| Parameter | Default | Effect |
|---|---|---|
| `GAMMA_S` | 0.15 | Steeper → short rest adds more training stress |
| `S_REST_MAX` | 1.5 | Cap on stress multiplier from short rest |

---

## 12. Load Stress Multiplier (`physiology.py`)

**load_stress_multiplier**
```
S_load = ((bw + load) / bw_ref)^GAMMA_LOAD
```
| Parameter | Default | Effect |
|---|---|---|
| `GAMMA_LOAD` | 1.5 | Superlinear; added weight stresses the system more than proportionally |

---

## 13. Grip Stress Multiplier (`physiology.py`)

**grip_stress_multiplier**
```
S_grip = GRIP_STRESS_FACTORS[grip]
```
| Parameter | Default | Effect |
|---|---|---|
| `GRIP_STRESS_FACTORS["pronated"]` | 1.00 | Baseline stress |
| `GRIP_STRESS_FACTORS["neutral"]` | 0.95 | Slightly lower stress (easier mechanically) |
| `GRIP_STRESS_FACTORS["supinated"]` | 1.05 | Slightly higher stress |

---

## 14. Session Training Load (`physiology.py`)

**calculate_session_training_load**
```
HR_j = actual_reps_j * E_rir(rir_j)
w(t) = sum_j( HR_j * S_rest(rest_j) * S_load(bw, load_j, bw_ref) * S_grip(grip) )
```
If `rir_j` is not reported, `RIR_hat = clip(M_hat - reps_j, 0, 5)` is used.

---

## 15. Fitness–Fatigue Model (`physiology.py`)

**update_fitness_fatigue** (one training day)
```
G(t) = G(t-1) * e^(-days / TAU_FITNESS)  + K_FITNESS * w(t)
H(t) = H(t-1) * e^(-days / TAU_FATIGUE)  + K_FATIGUE * w(t)
R(t) = G(t) - H(t)
```
**decay_fitness_fatigue** (rest days, w = 0)
```
G(t) = G(t-1) * e^(-days / TAU_FITNESS)
H(t) = H(t-1) * e^(-days / TAU_FATIGUE)
```
| Parameter | Default | Effect |
|---|---|---|
| `TAU_FITNESS` | 42 days | Longer → fitness accumulates and dissipates slowly |
| `TAU_FATIGUE` | 7 days | Shorter → fatigue clears within ~1–2 weeks |
| `K_FITNESS` | 0.5 | Fitness gain per unit load |
| `K_FATIGUE` | 1.0 | Fatigue gain per unit load; > K_FITNESS → net readiness drops after training |

**readiness** (from `FitnessFatigueState`)
```
R(t) = G(t) - H(t)
z    = (R(t) - readiness_mean) / sqrt(readiness_var)
```
Running stats use EWMA with α = 0.1 (hardcoded in `update_fitness_fatigue`).

---

## 16. Max Estimate EWMA (`physiology.py`)

**update_max_estimate**
```
M_hat_new  = (1 - ALPHA_MHAT) * M_hat + ALPHA_MHAT * M_obs
sigma²_new = (1 - BETA_SIGMA) * sigma² + BETA_SIGMA * (M_obs - M_hat)²
```
| Parameter | Default | Effect |
|---|---|---|
| `ALPHA_MHAT` | 0.25 | Higher → M_hat tracks recent tests faster, more volatile |
| `BETA_SIGMA` | 0.15 | Higher → uncertainty estimate reacts faster to outlier tests |
| `INITIAL_SIGMA_M` | 1.5 | Starting uncertainty (reps) for a new user |

---

## 17. Readiness-Adjusted Max (`physiology.py`)

**predicted_max_with_readiness**
```
M_pred = M_hat * (1 + C_READINESS * (R(t) - R_bar))
```
| Parameter | Default | Effect |
|---|---|---|
| `C_READINESS` | 0.02 | Scale of daily readiness swing on max prediction; keep small |

---

## 18. Plateau Detection (`adaptation.py`)

**detect_plateau**
```
slope = trend_slope_per_week(history, TREND_WINDOW_DAYS)
plateau = (slope < PLATEAU_SLOPE_THRESHOLD)
        AND (no TEST session in last PLATEAU_WINDOW_DAYS with max_reps >= all-time best)
```
| Parameter | Default | Effect |
|---|---|---|
| `PLATEAU_SLOPE_THRESHOLD` | 0.05 reps/week | Lower → harder to call plateau |
| `PLATEAU_WINDOW_DAYS` | 21 days | Shorter → plateau called sooner without a new PR |

---

## 19. Fatigue Score (`adaptation.py`)

**calculate_fatigue_score**
```
fatigue_score = (actual_max - M_pred) / M_pred
```
Positive = overperforming, negative = underperforming relative to the readiness-adjusted prediction.

---

## 20. Underperformance Check (`adaptation.py`)

**check_underperformance**
```
threshold = M_pred * (1 - UNDERPERFORMANCE_THRESHOLD)
underperforming if: last N S-sessions all have max_reps < threshold
```
| Parameter | Default | Effect |
|---|---|---|
| `UNDERPERFORMANCE_THRESHOLD` | 0.10 | 10% below predicted triggers flag; lower → more sensitive |

Default `consecutive_required = 2`.

---

## 21. Deload Triggers (`adaptation.py`)

**should_deload** — fires if ANY of:
```
1. detect_plateau(history) AND readiness_z_score < FATIGUE_Z_THRESHOLD
2. check_underperformance(history, ff_state)
3. weekly_compliance(history) < COMPLIANCE_THRESHOLD
```
| Parameter | Default | Effect |
|---|---|---|
| `FATIGUE_Z_THRESHOLD` | -0.5 | Less negative → deload triggered more easily with plateau |
| `COMPLIANCE_THRESHOLD` | 0.70 | Higher → deload triggered by smaller shortfall |

---

## 22. Volume Adjustment (`adaptation.py`)

**calculate_volume_adjustment**
```
if deload:         sets = max(WEEKLY_HARD_SETS_MIN, floor(sets * (1 - DELOAD_VOLUME_REDUCTION)))
elif z < Z_LOW:    sets = max(WEEKLY_HARD_SETS_MIN, floor(sets * (1 - READINESS_VOLUME_REDUCTION)))
elif z > Z_HIGH
 and compliance > 0.9:
                   sets = min(WEEKLY_HARD_SETS_MAX, floor(sets * (1 + WEEKLY_VOLUME_INCREASE_RATE)))
else:              sets = sets  (no change)
```
| Parameter | Default | Effect |
|---|---|---|
| `DELOAD_VOLUME_REDUCTION` | 0.40 | 40% cut during deload |
| `READINESS_VOLUME_REDUCTION` | 0.30 | 30% cut on a low-readiness day |
| `WEEKLY_VOLUME_INCREASE_RATE` | 0.10 | 10% increase when readiness is high |
| `WEEKLY_HARD_SETS_MIN` | 8 | Absolute floor regardless of reductions |
| `WEEKLY_HARD_SETS_MAX` | 20 | Absolute ceiling regardless of increases |

---

## 23. Autoregulation (`adaptation.py`)

**apply_autoregulation**
```
z = readiness_z_score()

if z < READINESS_Z_LOW:   sets = max(3, floor(base_sets * (1 - READINESS_VOLUME_REDUCTION)))
                          reps = base_reps  (unchanged)
elif z > READINESS_Z_HIGH: sets = base_sets
                           reps = base_reps + 1
else:                      (sets, reps) = (base_sets, base_reps)
```
| Parameter | Default | Effect |
|---|---|---|
| `READINESS_Z_LOW` | -1.0 | Below this z → reduce sets |
| `READINESS_Z_HIGH` | 1.0 | Above this z → add 1 rep |
| `READINESS_VOLUME_REDUCTION` | 0.30 | How much to cut when readiness is low |

Minimum 3 sets even at extreme low readiness.

---

## 24. Progression Rate (`config.py`)

**expected_reps_per_week**
```
fraction = 1 - (TM / TARGET_MAX_REPS)
delta    = DELTA_PROGRESSION_MIN + (DELTA_PROGRESSION_MAX - DELTA_PROGRESSION_MIN) * fraction^ETA_PROGRESSION
```
| Parameter | Default | Effect |
|---|---|---|
| `TARGET_MAX_REPS` | 30 | Goal; progression approaches zero as TM nears this |
| `DELTA_PROGRESSION_MIN` | 0.3 reps/week | Floor rate near the goal |
| `DELTA_PROGRESSION_MAX` | 1.0 reps/week | Peak rate at low TM |
| `ETA_PROGRESSION` | 1.5 | Exponent; higher → deceleration kicks in earlier |

Example values: TM = 5 → ~0.97 reps/week · TM = 15 → ~0.68 · TM = 25 → ~0.36 · TM = 29 → ~0.30
