# Parallel Bar Dip

## Biomechanics

Approximately 91–92% of bodyweight is lifted during bar dips. The hands and
forearms (~5% BW) are fixed to the bars and not displaced; upper arms rotate
rather than translate, reducing their effective contribution. This matches
published biomechanical approximations (~91.5% BW for bar dips).

**bw_fraction = 0.92**

Source: McKenzie et al. (2022). *Bench, Bar, and Ring Dips: Kinematics and
Muscle Activity.* PMCID: PMC9603242.

## Variants

| Variant | Stress factor | Notes |
|---------|--------------|-------|
| standard | 1.00 | Upright torso, balanced tricep/pec activation |
| chest_lean | 0.97 | Forward lean; emphasises pecs; slightly easier |
| tricep_upright | 1.03 | Strict upright; harder for triceps |

## Grip rotation

| Session type | Cycle |
|-------------|-------|
| S (Strength) | standard → chest_lean → tricep_upright |
| H (Hypertrophy) | standard → chest_lean → tricep_upright |
| T (Technique) | standard → tricep_upright |
| E (Endurance) | standard (fixed) |
| TEST | standard (fixed) |

## Added weight formula

```
added_kg = round( (BW × 0.92 × 0.012 × (TM − 12)) × 2 ) / 2
```

Activates when TM > 12. Capped at 30 kg.

Example: TM=15, BW=82 kg → `82 × 0.92 × 0.012 × 3 = 2.72` → rounds to 2.5 kg.

## Test protocol

1. **Warm-up** — 5 min light cardio, 1 set of 5 easy dips with full ROM, rest 2 min.
2. **Test** — Standard variant, full ROM (upper arms parallel at bottom, full
   lockout at top). No kipping. Count clean reps only.
3. **Log** — `bar-scheduler log-session --exercise dip --session-type TEST --sets 'N@0/180'`

**Test frequency:** every 3 weeks.
