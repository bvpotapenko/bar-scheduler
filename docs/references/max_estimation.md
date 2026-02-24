# References — Between-Test Max Estimation (Track B)

Track B estimates a user's current max reps between formal TEST sessions, using data from
regular training sets.  Two independent methods are computed and shown side-by-side as
**FI-estimate / Nuzzo-estimate** in the `eMax` column of the plan table.

---

## Methods

### FI Method — Fatigue Index (Pekünlü & Atalağ 2013)

**Citation:**
Pekünlü E, Atalağ O. (2013). *Which fatigue index should be used to assess different protocols
of fatigue?* European Journal of Sport Science, 13(5):534–544. PMID: 24050474.
PubMed Central: [PMC3827769](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3827769/)

**Formula:**

```
FI_reps = 1 − mean(R₂ … Rₙ) / R₁
```

where R₁ = first-set actual reps, R₂…Rₙ = subsequent sets.

- FI close to 0  → low within-session fatigue → user had reserve in R₁ (RIR > 0)
- FI ≈ 0.3–0.4  → typical near-failure training
- FI > 0.4      → high fatigue, very near failure from set 1

**Estimation logic:**

1. PCr-correct R₁ for incomplete phosphocreatine recovery before the first set
   (using the Bogdanis 1995 table below).
2. Upward-adjust for reserve when FI is low (≤ 0.35).
3. `fi_est ≈ R₁_corrected × (1 + max(0, 0.35 − FI) × 0.6)`

---

### Nuzzo REPS~%1RM Method (Nuzzo et al. 2024)

**Citation:**
Nuzzo JL, Pinto MD, Nosaka K, Steele J. (2024). *Maximal number of repetitions at
percentages of the one repetition maximum: a meta-regression and moderator analysis.*
Sports Medicine. PMID: 37943461.
PubMed Central: [PMC10933212](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10933212/)

**Bench-press REPS~%1RM table (meta-regression means, Table 2):**

| %1RM | Mean reps | SD  |
|-----:|----------:|----:|
| 100  |       1.0 | 0.0 |
|  95  |       3.0 | 1.5 |
|  90  |       5.3 | 2.0 |
|  85  |       7.7 | 2.5 |
|  80  |      11.0 | 4.0 |
|  75  |      13.4 | 5.0 |
|  70  |      17.0 | 6.0 |
|  65  |      21.0 | 7.5 |
|  60  |      25.0 | 9.0 |
|  55  |      29.7 | 9.5 |
|  50  |      35.0 |10.0 |

**Adaptation for bodyweight reps:**

Since bodyweight is fixed, we treat the repetition count as the performance metric
analogous to load.  If the user can do R reps to failure at a given session, this
corresponds to exercising at approximately X% of their single-set maximum.

```
pct_1rm  = inverse_nuzzo_lookup(reps_to_failure)   # linear interpolation
nuzzo_est = round(reps_to_failure / pct_1rm)
```

Example: 10 reps to failure → ~80 %1RM → estimated max = 10 / 0.80 ≈ 13 reps.

**RIR estimation when not reported:**
If the user did not report RIR, the FI is used as a proxy:

```
rir_est = max(0, round((0.35 − FI) × 8))
```

A high FI (near-failure sets) gives RIR ≈ 0; a low FI (comfortable sets) gives RIR up to ~3.

> **Note:** The Nuzzo table is for bench press and may not capture the exact
> reps~intensity relationship for pull-ups or dips.  It is used as a principled
> upper-bound estimate.  Use Track A (AMRAP TEST sessions) for ground truth.

---

## PCr Recovery Correction — Bogdanis et al. 1995

**Citation:**
Bogdanis GC, Nevill ME, Boobis LH, Lakomy HK, Nevill AM. (1995).
*Recovery of power output and muscle metabolites following 10 s of maximal sprint
cycling in man.* Journal of Physiology, 482(Pt 2):467–480.
DOI: [10.1113/jphysiol.1995.sp020533](https://doi.org/10.1113/jphysiol.1995.sp020533)

**PCr resynthesis table (Figure 4, estimated values):**

| Rest (s) | PCr recovered |
|---------:|--------------:|
|        0 |            0% |
|       10 |           25% |
|       30 |           50% |
|       60 |           75% |
|       90 |           87% |
|      120 |           93% |
|      180 |           97% |
|      240 |           99% |
|      300 |          100% |

**Usage:**
When the first set of a session is preceded by less than 300 s of rest (e.g., after a
warm-up), the PCr recovery fraction is used to inflate the observed R₁ to the expected
fresh-muscle performance:

```
fresh_R1 = R1 / pcr_factor(rest_before_set1)
```

A session started 3+ minutes after warm-up uses pcr_factor ≈ 0.97 (≈ no correction).
If `rest_before_set1 = 0` (no logged rest), 180 s is assumed as a conservative warm-up.

---

## Two-Track Architecture

| Track   | Source                 | Trigger           | Output           |
|---------|------------------------|-------------------|------------------|
| Track A | TEST sessions (AMRAP)  | Scheduled / auto  | Ground-truth max |
| Track B | Regular training sets  | Every session ≥2  | FI-est / Nz-est  |

The `eMax` column in the plan table shows:

- **Past TEST rows** — actual max reps (Track A, ground truth)
- **Past non-TEST rows** — `fi_est/nz_est` (Track B, between-test inference)
- **Future rows** — plan projection `round(expected_TM / 0.90)`, floored at the latest Track A value
