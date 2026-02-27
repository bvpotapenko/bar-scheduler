# 1RM Estimation Formulas

## Overview

The `-t m` trajectory in `plot-max` shows a projected curve of how much **added weight** (kg) a user could lift for 1 repetition as their training max improves. This is computed using a **rep-range–aware blended formula** rather than the single Epley formula.

### Why Not Epley Alone?

The Epley formula (`1RM = w × (1 + r/30)`) is **linear in reps**: `added_kg = bw_load × r / 30`. On a chart with a proportional right axis this means the m-trajectory and z-trajectory (bodyweight reps) always land at **identical grid positions** — the two curves look the same.

Non-linear formulas (Lombardi, Brzycki, Lander) give different marginal 1RM per rep at different rep ranges, producing a visually distinct m-curve that **bends and flattens** as reps approach 20.

---

## Formula Definitions

### Epley (1985)

```
1RM = w × (1 + r / 30)
```

General-purpose, widely used, but increasingly inaccurate above r ≈ 10.

### Lombardi (1989)

```
1RM = w × r^0.10
```

Power-curve formula; performs better than Epley for higher rep ranges (r > 10).
At r = 15: `1RM ≈ w × 1.311` (Epley gives `w × 1.500`).

### Brzycki (1993)

```
1RM = w / (1.0278 − 0.0278 × r)
```

Hyperbolic formula; accurate for r ≤ 10.
Denominator → 0 as r → 37 (physiologically irrelevant in practice).

### Lander (1985)

```
1RM = 100 × w / (101.3 − 2.67123 × r)
```

Rational formula; accurate for r ≤ 10.

---

## Rep-Range–Aware Blend (`blended_1rm_added`)

The function `blended_1rm_added(bw_load_kg, reps)` selects formulas by rep range to minimise estimation error:

| Rep range | Formulas blended               | Rationale                         |
|-----------|-------------------------------|-----------------------------------|
| r ≤ 5     | avg(Brzycki, Lander)          | Both accurate for low reps        |
| r ≤ 10    | avg(Brzycki, Lander, Epley)   | Epley adds stability              |
| 11 ≤ r ≤ 20 | avg(Lombardi, Epley)        | Lombardi corrects Epley's overestimate at high reps |
| r > 20    | `None` (unreliable)           | All formulas degrade above r = 20 |

The function returns **added kg only** (total 1RM − bw_load), so the right axis directly shows how much weight the user could strap on and still complete one rep.

---

## REPS ~ %1RM Reference Table

Based on Nuzzo et al. (2024, PMC10933212):

| Reps to failure | % 1RM |
|-----------------|-------|
| 1               | 100%  |
| 3               | 93%   |
| 5               | 87%   |
| 6               | 85%   |
| 8               | 80%   |
| 10              | 75%   |
| 12              | 70%   |
| 15              | 65%   |
| 20              | 58%   |

---

## Chart Implementation

- The m-trajectory is computed in `cli/commands/analysis.py` using `blended_1rm_added` on each point of the projected BW-reps trajectory (`base_pts`), capped at r = 20.
- The right axis in `core/ascii_plot.py` is calibrated **independently** from the m-trajectory's own kg range (0 → max_m_val × 1.1), so m dots land at different grid positions than z dots.
- m dots use the `○` marker; z dots use `·`; g dots use `×`.

---

## References

- Epley B. (1985). *Poundage Chart*. Boyd Epley Workout.
- Lombardi V. (1989). *Beginning Weight Training*. WCB Publishers.
- Brzycki M. (1993). *Strength Testing — Predicting a One-Rep Max from Reps-to-Fatigue*. JOPERD.
- Lander J. (1985). *Maximums Based on Reps*. NSCA Journal.
- Nuzzo JL, et al. (2024). *Absolute Strength, the Number of Repetitions Performed at a Given Percentage of 1-Repetition Maximum, and the Percentage of 1-Repetition Maximum at Which Fatigue Occurs*. PMC10933212.
- Pekünlü E. & Atalağ O. (2013). *Which Equation Is More Accurate in Predicting the 1 RM for the Bench Press?* PMC3827769.
