# Assessment Protocols

## Pull-Up Max Rep Test

**Frequency:** every 3 weeks

### Protocol
1. **Warm-up** — 2 min arm circles, 1 set of 5 easy pull-ups, rest 2 min.
2. **Test** — Dead hang, pronated grip, shoulder-width. Pull until chin clears
   the bar. Lower to full extension each rep. No kipping. Count clean reps only.
3. **Log** — `bar-scheduler log-session --session-type TEST --sets 'N@0/180'`

### Notes
- Same day and time of day where possible.
- Well-rested (no hard training within 48 h).
- Stop the set when form breaks down, not just at muscular failure.

---

## Parallel Bar Dip Max Rep Test

**Frequency:** every 3 weeks

### Protocol
1. **Warm-up** — 5 min light cardio, 1 set of 5 easy dips (full ROM), rest 2 min.
2. **Test** — Standard variant, full ROM: upper arms parallel at bottom, full
   lockout at top. No kipping. Count clean reps only.
3. **Log** — `bar-scheduler log-session --exercise dip --session-type TEST --sets 'N@0/180'`

### Notes
- Use the same bar width across all tests.
- Stop when you cannot complete a full lockout at the top.

---

## Bulgarian Split Squat Max Rep Test

**Frequency:** every 4 weeks

### Protocol
1. **Warm-up** — 5 min light cardio, 1 set of 10 BW BSS per leg, rest 2 min.
2. **Choose dumbbell weight** — A weight you expect to complete 8–20 reps with.
3. **Test** — Standard variant (rear foot flat on bench). Max reps per leg with
   full ROM (back knee near floor, front shin vertical). Count clean reps only.
   Test both legs; record the **weaker leg's** count.
4. **Log** — `bar-scheduler log-session --exercise bss --session-type TEST --sets 'N@<kg>/180'`

   Example: 15 reps with 24 kg DBs: `--sets '15@24/180'`

### Notes
- The dumbbell weight you test at becomes the training weight until the next TEST.
- Rest ≥ 3 min between legs.
- If testing both legs, rest 5 min before the second leg.
