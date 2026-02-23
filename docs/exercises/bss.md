# Bulgarian Split Squat (Dumbbell)

## Biomechanics

BSS is a unilateral, hip-dominant exercise performed with dumbbells. Bodyweight
is NOT included in the 1RM calculation — the load is the dumbbell weight only,
matching standard DB-exercise conventions.

**bw_fraction = 0.0** (external load only)

Sources:
- Mackey & Riemann (2021). *Biomechanical Differences Between the Bulgarian
  Split-Squat and Back Squat.* Int J Exerc Sci, 14(1):533–543.
- Song et al. (2023). *Effects of step lengths on biomechanical characteristics
  in split squat.* Front Bioeng Biotechnol, 11:1277493.

## Variants

| Variant | Stress factor | Notes |
|---------|--------------|-------|
| standard | 1.00 | Rear foot flat on bench |
| deficit | 1.05 | Front foot elevated; greater ROM |
| front_foot_elevated | 0.97 | Front foot raised; shorter ROM |

## Grip rotation

| Session type | Cycle |
|-------------|-------|
| S (Strength) | standard → deficit → front_foot_elevated |
| H (Hypertrophy) | standard → deficit → front_foot_elevated |
| T (Technique) | standard → deficit |
| E (Endurance) | standard (fixed) |
| TEST | standard (fixed) |

## Weight prescription

BSS uses the dumbbell weight from the most recent TEST session for all
training sessions. `weight_tm_threshold = 999` — auto-weight-from-TM never
triggers.

To change the training weight, log a new TEST session with the desired dumbbell
weight.

## Unilateral display

Each prescribed "set" means one set **per leg**. The plan output appends
**(per leg)** to every prescription. The configured rest interval is the rest
*between legs*; rest between full rounds is longer.

## 1RM estimate

```
1RM = added_weight_kg × (1 + reps / 30)   [Epley]
```

Bodyweight is NOT included (external-only convention).

## Test protocol

1. **Warm-up** — 5 min light cardio, 1 set of 10 BW BSS per leg, rest 2 min.
2. **Test** — Standard variant, chosen dumbbell weight, max reps per leg with
   full ROM (back knee near floor, front shin vertical). Count clean reps only.
3. **Log** — `bar-scheduler log-session --exercise bss --session-type TEST --sets 'N@<kg>/180'`

   Example: 15 reps with 24 kg DBs: `--sets '15@24/180'`

**Test frequency:** every 4 weeks.
