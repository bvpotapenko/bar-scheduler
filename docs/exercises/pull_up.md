# Pull-Up

## Biomechanics

During a strict pull-up, near-100% of bodyweight is displaced vertically.
The hands and forearms are fixed to the bar and move with the body; upper-arm
rotation contributes to vertical displacement. A small correction for distal
forearm mass (~2–3%) is ignored for practical purposes.

**bw_fraction = 1.0**

## Variants

| Variant | Stress factor | Notes |
|---------|--------------|-------|
| pronated | 1.00 | Standard overhand grip — primary test variant |
| neutral | 1.00 | Parallel / hammer grip |
| supinated | 1.00 | Underhand / chin-up grip |

All three variants have the same normalisation factor (1.0) because the
BW-equivalent load is identical; differences are muscular emphasis, not
total load.

## Grip rotation

| Session type | Cycle |
|-------------|-------|
| S (Strength) | pronated → neutral → supinated |
| H (Hypertrophy) | pronated → neutral → supinated |
| T (Technique) | pronated → neutral |
| E (Endurance) | pronated (fixed) |
| TEST | pronated (fixed) |

## Added weight formula

```
added_kg = round( (BW × 0.01 × (TM − 9)) × 2 ) / 2
```

Activates when TM > 9. Capped at 20 kg.

## Test protocol

1. **Warm-up** — 2 min arm circles, 1 set of 5 easy pull-ups, rest 2 min.
2. **Test** — Dead hang, pronated grip, shoulder-width. Pull until chin clears
   the bar. Lower to full extension each rep. No kipping. Count clean reps only.
3. **Log** — `bar-scheduler log-session --session-type TEST --sets 'N@0/180'`

**Test frequency:** every 3 weeks.
