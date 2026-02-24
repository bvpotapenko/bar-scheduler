# Adaptation Guide: How the Planner Learns from Your Data

This guide explains what the planner can and cannot do at each stage of your
training history. Understanding the timeline helps you set realistic expectations
and get the most out of the model.

> **Quick access:** `bar-scheduler help-adaptation`

---

## Adaptation Stages

```
┌─────────────────┬──────────────────────────────────────────────────────┐
│ Stage           │ What the model can do                                │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Day 1           │ Generic safe plan from your baseline max.            │
│ (no history)    │ Conservative volume. No weighted work until TM > 9.  │
│                 │ RECOMMENDATION: Just follow the plan and log.        │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 1–2       │ EWMA max estimate starts tracking.                   │
│ (3–8 sessions)  │ Rest normalization active (short rest gets credit).  │
│                 │ NO autoregulation yet (not enough data).             │
│                 │ RECOMMENDATION: Log rest times accurately.           │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 3–4       │ AUTOREGULATION ACTIVATES (≥10 sessions).             │
│ (10–16 sessions)│ Plateau detection possible.                          │
│                 │ Rest adaptation kicks in (RIR + drop-off based).     │
│                 │ RECOMMENDATION: Do your first re-test (TEST session).│
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 6–8       │ Individual fatigue profile fitted.                   │
│ (24–32 sessions)│ Set-to-set predictions improve.                      │
│                 │ Deload triggers become reliable.                     │
│                 │ RECOMMENDATION: Trust the deload if recommended.     │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 12+       │ Full training profile established.                   │
│ (48+ sessions)  │ Long-term fitness adaptation curve accurate.         │
│                 │ Progression rate calibrated to your response.        │
│                 │ RECOMMENDATION: Model is at peak accuracy.           │
└─────────────────┴──────────────────────────────────────────────────────┘
```

---

## What Happens Inside

### Day 1 — Baseline only

At initialisation (`bar-scheduler init`), you provide a **baseline max** — the
number of strict reps you can do today.  The planner:

- Sets your **Training Max (TM)** = `floor(0.9 × baseline_max)`.
- Starts a conservative 3-week plan: Strength → Hypertrophy → Endurance.
- Prescribes bodyweight-only sets (no added weight until TM > 9).
- Generates a basic fitness-fatigue state with near-zero fitness and fatigue.

### Weeks 1–2 — EWMA calibration

Each logged session updates an **EWMA max estimate** (`m_hat`), a running
weighted average of your performance.  After 3–8 sessions:

- `m_hat` converges to a reliable estimate of your current max.
- **Rest normalization** adjusts standardised reps — a set with 90 s rest
  counts less than the same reps with 180 s rest.
- **Autoregulation is not yet active** (requires ≥ 10 sessions as a gate).

### Weeks 3–4 — Autoregulation unlocks

After **10 sessions**, autoregulation activates:

- Sets and reps adapt to your **readiness z-score** (derived from the
  fitness-fatigue model).
- Low readiness (z < −1) → reduced volume.
- High readiness (z > +1) → bonus rep added to target sets.
- **Adaptive rest** kicks in: rest intervals respond to your last session's
  RIR, drop-off ratio, and readiness z-score.

This is also a good time for your **first periodic re-test** (TEST session),
which anchors the EWMA estimate precisely.

### Weeks 6–8 — Individual fatigue profile

With 24–32 sessions:

- The fitness-fatigue state has enough history to fit your individual
  fatigue and fitness time constants.
- **Set-to-set predictions** become more accurate.
- **Deload recommendations** are reliable (plateau detection + fatigue score
  both need sufficient history to avoid false positives).

### Weeks 12+ — Full profile

After 48+ sessions the model is operating at peak accuracy:

- Your personal progression rate is calibrated from real data.
- Long-term fitness adaptation curve is accurate enough to project your
  target date reliably.
- The `plot-max --trajectory` command shows a realistic forecast.

---

## Tips for Best Results

| What to do | Why |
|-----------|-----|
| Log **every** session, including bad ones | Low-RIR / incomplete sets = critical fatigue data |
| Log **rest times**, even approximately | Rest normalization and adaptive rest depend on this |
| Do a **TEST session every 3–4 weeks** | Anchors m_hat; prevents EWMA drift |
| Update **bodyweight** when it changes ≥ 1 kg | Load stress calculations use current BW |
| Don't skip logging after a deload | The model needs to see the recovery signal |
| Trust **plan changes** after a TEST | Past prescriptions are frozen; future sessions adapt |

---

## Multi-Exercise Notes

Each exercise (`pull_up`, `dip`, `bss`) has its **own** adaptation timeline:

- Separate history files → separate fitness-fatigue states.
- Separate TEST schedules (pull-ups/dips: every 3 weeks; BSS: every 4 weeks).
- Autoregulation activates per-exercise at 10 sessions each.

If you start dips six weeks after pull-ups, your dip plan will be at "Day 1"
accuracy while your pull-up plan is in the "Weeks 6–8" phase.

---

## Related Commands

```bash
bar-scheduler help-adaptation      # This guide in the terminal
bar-scheduler status               # Current readiness, TM, trend
bar-scheduler plot-max --trajectory  # Projected goal completion date
bar-scheduler explain next         # Why today's session is planned this way
```
