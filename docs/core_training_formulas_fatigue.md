
# CORE research: formulas & rules for pull-up plan generation and fatigue accounting

Scope: this document defines the **adjustable mathematical rules** (not UI) for the core engine that (a) estimates current pull-up performance from history, (b) quantifies training load, (c) models fatigue/readiness over time, and (d) generates the next multi-week schedule toward a target of 30 strict pull-ups.

This is intentionally “parameterized”: constants live in `core/config.py` so the model can be tuned if it is too aggressive or too conservative.

---

## 1) Notation & definitions

### 1.1 Standardized test definition

All “max reps” comparisons should be standardized to:

- Movement: strict pull-up, dead hang → chin over bar.
- Grip: **pronated** (palms forward).
- External load: **0 kg**.
- Inter-set rest reference: **180 s** (used only for normalization).

### 1.2 Session record fields (minimum for the model)

For each training session `s` logged at date `d`:

- `bw(d)`: bodyweight (kg) at that date (or nearest known).
- For each set `j`:
  - `reps_j` (integer)
  - `rest_j` seconds (time between set j-1 and set j; for set 1, store warm-up rest or set to reference)
  - `load_j` added load (kg), 0 for bodyweight-only
  - `grip_j` in {pronated, neutral, supinated}
  - optional `rir_j` reported repetitions-in-reserve.

---

## 2) Normalization: comparing sessions with different rest, load, grip, and bodyweight

The core needs a single “comparable” performance variable: an estimate of **fresh standardized max reps** on the reference test, called `M_hat(d)`.

### 2.1 Rest normalization (set-to-set)

Inter-set rest changes both achievable reps and the fatigue state. Evidence indicates shorter rest (≈≤60 s) can impair outcomes compared with longer rest, and a trial comparing 1 min vs 3 min showed greater strength (and some hypertrophy outcomes) with 3 min when other variables were controlled.

Use a conservative, monotonic rest factor that:

- Saturates for long rests (beyond ~180 s) to avoid over-crediting very long rests.
- Penalizes very short rests (<60–90 s) more strongly.

Recommended functional form:

\[
F_{rest}(r) = \mathrm{clip}\Big(\big(\tfrac{r}{r_{ref}}\big)^{\gamma_r},\;F_{min},\;F_{max}\Big)
\]

Where:

- `r` = rest seconds between sets.
- `r_ref` = 180.
- `gamma_r` default 0.15–0.30.
- `F_min` default 0.80.
- `F_max` default 1.05.

Interpretation: if `r < r_ref`, `F_rest < 1` (short rest makes reps “harder”), so the set’s normalized reps are larger than observed.

Define rest-normalized reps:

\[
reps^*_j = \frac{reps_j}{F_{rest}(rest_j)}
\]

### 2.2 Bodyweight normalization

Pull-ups are a strength-to-mass task. If bodyweight increases while strength stays constant, max reps usually decreases.

Define a reference bodyweight `bw_ref` as the **latest** user bodyweight (or a chosen baseline). Convert each set’s effective relative load:

\[
L_{rel,j} = \frac{bw(d) + load_j}{bw_{ref}}
\]

Convert to a bodyweight-normalized rep estimate:

\[
reps^{**}_j = reps^*_j \cdot L_{rel,j}^{\gamma_{bw}}
\]

- `gamma_bw` default 0.8–1.2.
- If `bw(d)` is higher than `bw_ref`, then `L_rel>1` and `reps**` is scaled upward to estimate what the set might look like at `bw_ref`.

### 2.3 Grip normalization (optional, configurable)

Grip changes mechanics and may affect reps and joint stress.

Use a simple multiplicative mapping to the pronated standard:

- pronated: `F_grip = 1.00`
- neutral: `F_grip = 0.98–1.02` (config)
- supinated: `F_grip = 0.95–1.05` (config)

Then:

\[
reps^{std}_j = reps^{**}_j \cdot F_{grip}
\]

Practical note: keep grip factors close to 1.0 by default and let the model learn from history; otherwise you can accidentally “bake in” wrong assumptions.

---

## 3) Estimating the current standardized max reps, M_hat

The simplest robust estimator should:

- Prefer recent, higher-quality evidence.
- Down-weight sessions with very short rest, high fatigue, or non-standard grips.
- Produce an uncertainty value.

### 3.1 Candidate per-session max estimate

For each session date `d`, compute the best per-session standardized set performance:

\[
X(d) = \max_j\; reps^{std}_j
\]

Then infer standardized max `M(d)` from `X(d)` using a bounded mapping.

Option A (minimal assumption): treat `X(d)` as a noisy direct observation of max.

\[
M_{obs}(d) = X(d)
\]

Option B (if RIR logged): if a set has `rir_j`, estimate the corresponding “to-failure” reps:

\[
M_{obs}(d) = \max_j (reps^{std}_j + rir_j)
\]

### 3.2 Exponentially weighted moving average (EWMA)

Maintain `M_hat(d)` as an EWMA over observations:

\[
M_{hat}(d_k) = (1-\alpha)\,M_{hat}(d_{k-1}) + \alpha\,M_{obs}(d_k)
\]

- `alpha` default 0.20–0.35.
- Initialize `M_hat` from the baseline max if no history.

### 3.3 Uncertainty

Track dispersion of residuals:

\[
\sigma_M^2 \leftarrow (1-\beta)\,\sigma_M^2 + \beta\,(M_{obs}-M_{hat})^2
\]

- `beta` default 0.10–0.25.
- Use `sigma_M` to slow progression when uncertainty is high.

---

## 4) Two-timescale fatigue/readiness model (fitness–fatigue impulse response)

A well-established approach in training monitoring is to model performance as the difference between a **longer-lasting positive adaptation** (fitness) and a **shorter-lasting negative adaptation** (fatigue), both driven by training impulses with exponential decay. This “fitness–fatigue” or impulse-response framework is described in the Banister lineage and later analyses/reviews.

### 4.1 Daily impulse-response equations (discrete time)

Let `w(t)` be the training load impulse on day `t` (0 if rest day).

Maintain two state variables:

- Fitness `G(t)` (slow decay)
- Fatigue `H(t)` (fast decay)

Update:

\[
G(t) = G(t-1)\,e^{-1/\tau_G} + k_G\,w(t)
\]

\[
H(t) = H(t-1)\,e^{-1/\tau_H} + k_H\,w(t)
\]

Readiness (predicted ability to perform) is:

\[
R(t) = R_0 + G(t) - H(t)
\]

Typical parameter logic:

- `tau_H` (fatigue time constant) shorter than `tau_G`.
- `k_H` often larger than `k_G` (training creates fatigue strongly and quickly).

Recommended defaults (tunable):

- `tau_H` = 5–9 days
- `tau_G` = 30–50 days
- `k_H / k_G` = 1.5–3.0

These defaults are consistent with common impulse-response parameterizations used in applied monitoring literature and discussions of the Banister model family.

### 4.2 Linking readiness to pull-up max

Convert readiness to a multiplicative factor on standardized max:

\[
M_{pred}(t) = M_{base}(t) \cdot (1 + c_R\,(R(t)-\bar{R}))
\]

- `M_base(t)` is the slowly evolving EWMA estimate from §3.
- `c_R` small (e.g., 0.01–0.03).
- `\bar{R}` is a rolling mean of readiness.

This makes the fatigue model influence *day-to-day prescription* without overriding the long-term trend.

---

## 5) Defining training load w(t) from pull-up sessions

The impulse-response model requires a scalar `w(t)` that increases when training is more stressful.

Because pull-ups are bodyweight-based and also skill-specific, define load from **effective hard reps**, weighted by proximity to failure and rest.

### 5.1 Set difficulty weight via RIR

If `rir_j` is known, define effort multiplier:

\[
E_{rir}(rir) = 1 + a\,\max(0, 3-rir)
\]

- Example: RIR 3 → 1.0, RIR 2 → 1.0+a, RIR 0 → 1.0+3a.
- `a` default 0.10–0.25.

If `rir_j` missing, estimate it from rep fraction of estimated max:

\[
\widehat{rir}_j = \mathrm{clip}(M_{hat}(d) - reps^{std}_j,\;0,\;5)
\]

### 5.2 Rest stress multiplier

Short rest can increase local fatigue for a given number of reps and may require more sets to reach similar hypertrophy responses, while very short rests can impair performance.

Use:

\[
S_{rest}(r) = \mathrm{clip}\Big(\big(\tfrac{r_{ref}}{\max(r, r_{min})}\big)^{\gamma_s},\;1,\;S_{max}\Big)
\]

- `r_ref` = 180 s, `r_min` = 30 s.
- `gamma_s` default 0.10–0.25.
- `S_max` default 1.5.

If rests are long (≥180 s), `S_rest≈1`; if rests are short, stress per rep rises.

### 5.3 Relative load multiplier (weighted pull-ups)

For a set with added load, compute:

\[
S_{load} = (L_{rel,j})^{\gamma_L}
\]

- `L_rel` defined in §2.2.
- `gamma_L` default 1.0–2.0.

### 5.4 Session training impulse

Define effective hard reps:

\[
HR_j = reps_j \cdot E_{rir}(\widehat{rir}_j)
\]

Then the day impulse:

\[
w(t) = \sum_{j \in session(t)} HR_j \cdot S_{rest}(rest_j) \cdot S_{load}(j) \cdot S_{grip}(j)
\]

Where `S_grip` is a mild factor (≈1.0) if you want to reflect differing stress (e.g., supinated may be more biceps-dominant).

This definition ensures:

- More reps → higher impulse.
- Closer to failure → higher impulse.
- Shorter rests → higher impulse.
- Added load → higher impulse.

---

## 6) Within-session fatigue model (set-to-set drop-off)

For prescription you need a model of how reps decline across sets given rest.

### 6.1 Multiplicative decay with rest recovery

Let `p` be the “fresh capacity” in reps for the chosen variation at that time.

Predict set `j` reps (to a target RIR) using:

\[
reps_{pred,j} = \max\Big(0,\; \lfloor (p - RIR_{target}) \cdot e^{-\lambda\,(j-1)} \cdot Q_{rest}(rest_j) \rfloor \Big)
\]

Where:

\[
Q_{rest}(r) = 1 - q\,e^{-r/\tau_r}
\]

- `lambda` controls accumulation within session.
- `q` and `tau_r` shape how rest restores performance.

Fit `lambda` (and optionally `q`) from history by minimizing squared error between predicted and observed sets on sessions with known rest.

### 6.2 Session fatigue marker from observed drop-off

Compute drop-off:

\[
D = 1 - \frac{\mathrm{mean}(reps_{last2})}{reps_{set1}}
\]

Use `D` as an acute fatigue marker:

- If `D` is high (config threshold, e.g., >0.35) **and** rest is not extremely short, the athlete likely accumulated large fatigue.
- If `D` is high with very short rest, interpret as density stress (expected).

Feed this marker into the fatigue impulse `w(t)` (increase) and next-session prescription (reduce).

---

## 7) Plan generation rules (3–4 days/week) using the models above

### 7.1 Session archetypes

Use daily undulating structure to distribute stress and reduce monotony:

- **S (Strength)**: low reps, higher load, longer rest
- **H (Hypertrophy/Volume)**: moderate reps, moderate rest
- **E (Endurance/Density)**: submax repeated sets, short–moderate rest
- Optional **T (Technique/Easy)** for 4th day: low fatigue, high quality

### 7.2 Choosing weekly volume targets

For hypertrophy-oriented pulling, evidence syntheses suggest that per-session volumes often show diminishing returns past roughly 6–8 hard sets for a muscle group when rests are long, and weekly set ranges around ~12–24 sets when training 2–3×/week are common starting points (with strong individual variability and the need for small incremental changes).

Implement volume as **pull-up-pattern hard sets** per week:

- Start: 8–14 hard sets/week for this athlete.
- Increase by at most 10–20% when progress is good.
- Reduce 30–50% for deload.

### 7.3 Converting M_hat to prescriptions

Let `TM = floor(0.9 * M_hat)` as “training max reps” (submax anchor).

Then default targets:

- Strength day (S):
  - reps/set = `clip(round(0.35–0.55 * TM), 3, 6)`
  - sets = 4–7 (depending on fatigue state)
  - rest = 180–240 s
  - load selection rule: choose added load so that the prescribed reps hit RIR 2–3.

- Hypertrophy day (H):
  - reps/set = `clip(round(0.55–0.75 * TM), 6, 12)`
  - sets = 4–8
  - rest = 120–180 s

- Endurance day (E):
  - total reps target = `kE * TM` where `kE` grows with level (e.g., 3.0→5.0)
  - implement as multiple sets of `round(0.35–0.55 * TM)` with 45–90 s rest

- Technique day (T, optional):
  - 6–12 sets of 2–4 reps @ RIR 4–6, rest 60–120 s

### 7.4 Readiness gating (autoregulation)

Let `z = (R(t) - mean_R)/sd_R`.

- If `z < -1.0`: reduce planned pull-up hard sets by 25–40% and/or increase rest; avoid failure.
- If `-1.0 <= z <= 1.0`: execute base plan.
- If `z > 1.0` and last week compliance high: allow a small progression (e.g., +1 rep on 1–2 sets, or +1 set).

### 7.5 Progression rules toward 30

Because 29→30 is disproportionately hard, use a nonlinear progression limiter:

\[
\Delta TM_{week} = \Delta_{min} + (\Delta_{max}-\Delta_{min})\,(1 - TM/30)^{\eta}
\]

- Example defaults: `Delta_min=0.1`, `Delta_max=0.6`, `eta=1.5`.

Then:

- If achieved performance exceeds predicted by >1.0 reps and fatigue state low: add reps/sets next week up to cap.
- If underperforms for ≥2 exposures: hold or deload.

---

## 8) Plateau detection and deload rules

### 8.1 Plateau in standardized max

Using the series of `M_hat(d)` points, fit a short-window trend (e.g., last 14–28 days).

Plateau condition:

- slope < `slope_min` (e.g., <0.05 reps/week)
- AND no new best `M_obs` in `plateau_days` (e.g., 21 days)

### 8.2 Deload trigger

Trigger deload if any:

- Plateau AND readiness z-score is low (e.g., z < -0.5) for multiple days.
- Two consecutive strength sessions with large underperformance vs `M_pred` (e.g., -10% reps) with adequate rest.
- Compliance ratio <0.7 for a week (suggests plan too hard).

Deload prescription:

- Reduce weekly hard sets by 30–50%.
- Keep intensity moderate (do not add load).
- Increase rest intervals (move toward 180 s).

---

## 9) Practical parameter initialization for “no history”

If no history exists:

1. Ask for baseline strict max `M0`.
2. Initialize:
   - `M_hat = M0`
   - `sigma_M = 1.5` reps (high uncertainty)
   - `G=0`, `H=0`
3. Generate a 2-week calibration block:
   - Week template: S / H / E
   - Use conservative volumes: 8–10 hard sets/week
   - Force standardized rests for the first week to collect good data (≥120 s on S/H)

---

## 10) What this model buys the software

- A principled way to incorporate **rest between sets** into both performance estimation and fatigue accumulation.
- A simple, explainable state-space model (fitness vs fatigue) to drive day-to-day autoregulation.
- A clear path to incorporate more signals later (sleep, soreness, subjective readiness) by adding them to `w(t)` or to the gating logic.

---

## 11) Sources used (for engineering justification)

- Fitness–fatigue / impulse-response modeling background and analysis of the Banister model family are discussed in peer-reviewed open-access sources. Examples include: “Assessing the limitations of the Banister model in monitoring training” (1995) and later reviews on fitness–fatigue models and training-load response modeling.
- Rest interval effects: a controlled trial found longer inter-set rest (3 min) improved strength outcomes compared with 1 min under matched conditions; and a 2024 systematic review with Bayesian meta-analysis suggests only small hypertrophy differences across rest intervals and diminishing differences beyond roughly ~90 s.
- Autoregulation / RIR nuance: a 2025 open-access paper shows perceived RIR relates to objective velocity but is influenced by load, set number, and other variables, supporting cautious use and context-dependent interpretation.

(Implementation note: keep full links in the repository `docs/` and avoid embedding long copyrighted text.)
