"""
Profile 1 constants — 50 kg / 160 cm.
Exercises: dip (1 day/wk) + incline_db_press (2 days/wk) + bss (3 days/wk).

Section A: hand-authored (profile config, equipment, test-session inputs).
Section B: GENERATED — run regenerate.py to fill in expected planner output.
"""

# ===========================================================================
# Section A: hand-authored
# ===========================================================================

P1_HEIGHT_CM = 160
P1_BODYWEIGHT_KG = 50.0

# --- exercise training days ---
P1_DIP_DAYS = 1
P1_INCLINE_DAYS = 2
P1_BSS_DAYS = 3

# --- exercise targets ---
P1_DIP_TARGET_REPS = 20
P1_DIP_TARGET_WEIGHT_KG = 0.0

P1_INCLINE_TARGET_REPS = 12
P1_INCLINE_TARGET_WEIGHT_KG = 10.0

P1_BSS_TARGET_REPS = 1
P1_BSS_TARGET_WEIGHT_KG = 120.0

# --- equipment ---
P1_DIP_AVAILABLE_ITEMS = ["MACHINE_ASSISTED", "BAND_SET", "PARALLEL_BARS"]
P1_DIP_MACHINE_ASSISTANCE_KG = [20, 25, 30, 35, 40, 45, 50, 55, 60]

P1_INCLINE_AVAILABLE_ITEMS = ["DUMBBELLS"]
P1_INCLINE_WEIGHTS_KG = [round(1.0 + i * 1.5, 1) for i in range(17)]  # 1.0 → 25.0 step 1.5

P1_BSS_AVAILABLE_ITEMS = ["DUMBBELLS"]
P1_BSS_WEIGHTS_KG = list(range(2, 38, 2))  # 2 → 36 step 2

# --- Layer 3: improved TEST sessions (date must be after last Layer-2 history entry) ---
P1_DIP_IMPROVED_TEST = {
    "date": "2026-01-11",
    "session_type": "TEST",
    "bodyweight_kg": 50.0,
    "sets": [{"reps": 6, "rest_seconds": 180, "added_weight_kg": 0.0, "rir_reported": None}],
    "grip": "standard",
}

P1_INCLINE_IMPROVED_TEST = {
    "date": "2026-01-11",
    "session_type": "TEST",
    "bodyweight_kg": 50.0,
    "sets": [{"reps": 12, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": None}],
    "grip": "standard",
}

P1_BSS_IMPROVED_TEST = {
    "date": "2026-01-11",
    "session_type": "TEST",
    "bodyweight_kg": 50.0,
    "sets": [{"reps": 8, "rest_seconds": 180, "added_weight_kg": 14.0, "rir_reported": None}],
    "grip": "standard",
}

# --- Layer 4: overperformance sessions (~1.5× the first prescribed S-session reps) ---
# Dates match the first planned session from Layer 2 (plan_start = 2026-01-13).
P1_INCLINE_OVERPERFORMANCE = {
    "date": "2026-01-13",
    "session_type": "S",
    "bodyweight_kg": 50.0,
    "sets": [
        {"reps": 8, "rest_seconds": 180, "added_weight_kg": 5.5, "rir_reported": 2},
        {"reps": 8, "rest_seconds": 180, "added_weight_kg": 5.5, "rir_reported": 2},
        {"reps": 8, "rest_seconds": 180, "added_weight_kg": 5.5, "rir_reported": 2},
        {"reps": 7, "rest_seconds": 180, "added_weight_kg": 5.5, "rir_reported": 2},
    ],
    "grip": "standard",
}

P1_BSS_OVERPERFORMANCE = {
    "date": "2026-01-13",
    "session_type": "S",
    "bodyweight_kg": 50.0,
    "sets": [
        {"reps": 8, "rest_seconds": 180, "added_weight_kg": 14.0, "rir_reported": 2},
        {"reps": 8, "rest_seconds": 180, "added_weight_kg": 14.0, "rir_reported": 2},
        {"reps": 7, "rest_seconds": 180, "added_weight_kg": 14.0, "rir_reported": 2},
        {"reps": 7, "rest_seconds": 180, "added_weight_kg": 14.0, "rir_reported": 2},
    ],
    "grip": "standard",
}

# --- Layer 5: 15-week incline_db_press simulation ---
# Fresh profile dir; sessions span 2025-10-01 → 2026-01-05 (before frozen today 2026-01-12).
# Phase 1 (sessions 1-7): normal load, rir=2 — should show no plateau.
# Phase 2 (sessions 8-14): dense, rir=0 — should trigger plateau + deload.
# Phase 3 (sessions 15-20): deload then recovery TEST — plateau resolves.
P1_INCLINE_15W_SESSIONS = [
    # ---- Phase 1: normal ----
    {"date": "2025-10-01", "session_type": "TEST", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-10-05", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 150, "added_weight_kg": 4.0, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 4.0, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 4.0, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 4.0, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-10-09", "session_type": "S", "bodyweight_kg": 50.0,
     "sets": [{"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-10-13", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-10-17", "session_type": "S", "bodyweight_kg": 50.0,
     "sets": [{"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-10-21", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-10-25", "session_type": "TEST", "bodyweight_kg": 50.0,
     "sets": [{"reps": 10, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 2}],
     "grip": "standard"},
    # ---- Phase 2: overtraining (session 8-14) ----
    {"date": "2025-10-29", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 8, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 8, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 7, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 7, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0}],
     "grip": "standard"},
    {"date": "2025-11-01", "session_type": "S", "bodyweight_kg": 50.0,
     "sets": [{"reps": 5, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 5, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 4, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 4, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 4, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0}],
     "grip": "standard"},
    {"date": "2025-11-03", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 7, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 7, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 6, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 6, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0}],
     "grip": "standard"},
    {"date": "2025-11-05", "session_type": "E", "bodyweight_kg": 50.0,
     "sets": [{"reps": 12, "rest_seconds": 45, "added_weight_kg": 4.0, "rir_reported": 0},
              {"reps": 11, "rest_seconds": 45, "added_weight_kg": 4.0, "rir_reported": 0},
              {"reps": 10, "rest_seconds": 45, "added_weight_kg": 4.0, "rir_reported": 0},
              {"reps": 10, "rest_seconds": 45, "added_weight_kg": 4.0, "rir_reported": 0},
              {"reps": 9,  "rest_seconds": 45, "added_weight_kg": 4.0, "rir_reported": 0},
              {"reps": 9,  "rest_seconds": 45, "added_weight_kg": 4.0, "rir_reported": 0}],
     "grip": "standard"},
    {"date": "2025-11-07", "session_type": "S", "bodyweight_kg": 50.0,
     "sets": [{"reps": 5, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 4, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 4, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 4, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0},
              {"reps": 3, "rest_seconds": 90, "added_weight_kg": 7.0, "rir_reported": 0}],
     "grip": "standard"},
    {"date": "2025-11-10", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 7, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 6, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 6, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 5, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0},
              {"reps": 5, "rest_seconds": 60, "added_weight_kg": 5.5, "rir_reported": 0}],
     "grip": "standard"},
    {"date": "2025-11-13", "session_type": "TEST", "bodyweight_kg": 50.0,
     "sets": [{"reps": 10, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 0}],
     "grip": "standard"},
    # ---- Phase 3: deload + recovery (sessions 15-20) ----
    {"date": "2025-11-21", "session_type": "E", "bodyweight_kg": 50.0,
     "sets": [{"reps": 10, "rest_seconds": 180, "added_weight_kg": 2.5, "rir_reported": 3},
              {"reps": 10, "rest_seconds": 180, "added_weight_kg": 2.5, "rir_reported": 3},
              {"reps": 10, "rest_seconds": 180, "added_weight_kg": 2.5, "rir_reported": 3}],
     "grip": "standard"},
    {"date": "2025-11-28", "session_type": "E", "bodyweight_kg": 50.0,
     "sets": [{"reps": 10, "rest_seconds": 180, "added_weight_kg": 2.5, "rir_reported": 3},
              {"reps": 10, "rest_seconds": 180, "added_weight_kg": 2.5, "rir_reported": 3},
              {"reps": 10, "rest_seconds": 180, "added_weight_kg": 2.5, "rir_reported": 3}],
     "grip": "standard"},
    {"date": "2025-12-05", "session_type": "E", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 3},
              {"reps": 8, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 3},
              {"reps": 8, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 3}],
     "grip": "standard"},
    {"date": "2025-12-12", "session_type": "H", "bodyweight_kg": 50.0,
     "sets": [{"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 8, "rest_seconds": 150, "added_weight_kg": 5.5, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2025-12-19", "session_type": "S", "bodyweight_kg": 50.0,
     "sets": [{"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2},
              {"reps": 5, "rest_seconds": 210, "added_weight_kg": 5.5, "rir_reported": 2}],
     "grip": "standard"},
    {"date": "2026-01-05", "session_type": "TEST", "bodyweight_kg": 50.0,
     "sets": [{"reps": 12, "rest_seconds": 180, "added_weight_kg": 4.0, "rir_reported": 2}],
     "grip": "standard"},
]

# checkpoint session indices (1-based) and expected values — GENERATED below
P1_INCLINE_15W_CHECKPOINT_IDX = [7, 14, 20]


# ===========================================================================
# Section B: GENERATED — do not hand-edit; run regenerate.py to refresh
# ===========================================================================

# --- Layer 2: plan status after baseline history ---
P1_DIP_STATUS = {'training_max': 2,
 'latest_test_max': 3,
 'trend_slope_per_week': 0.0,
 'is_plateau': False,
 'deload_recommended': True,
 'readiness_z_score': 1.2645,
 'fitness': 14.2334,
 'fatigue': 8.9459}
P1_INCLINE_STATUS = {'training_max': 7,
 'latest_test_max': 8,
 'trend_slope_per_week': 0.0,
 'is_plateau': False,
 'deload_recommended': True,
 'readiness_z_score': 1.8801,
 'fitness': 131.816,
 'fatigue': 94.1487}
P1_BSS_STATUS = {'training_max': 4,
 'latest_test_max': 5,
 'trend_slope_per_week': 0.0,
 'is_plateau': False,
 'deload_recommended': True,
 'readiness_z_score': 2.0189,
 'fitness': 186.3829,
 'fatigue': 147.7606}

# --- Layer 2: future session prescriptions ---
P1_DIP_FUTURE_SESSIONS = [{'date': '2026-01-13',
  'type': 'TEST',
  'prescribed_sets': [{'reps': 3, 'weight_kg': 0.0, 'rest_s': 240}]},
 {'date': '2026-01-20',
  'type': 'S',
  'prescribed_sets': [{'reps': 4, 'weight_kg': 0.0, 'rest_s': 240}]},
 {'date': '2026-01-27',
  'type': 'S',
  'prescribed_sets': [{'reps': 4, 'weight_kg': 0.0, 'rest_s': 240}]},
 {'date': '2026-02-03',
  'type': 'TEST',
  'prescribed_sets': [{'reps': 5, 'weight_kg': 0.0, 'rest_s': 240}]}]
P1_INCLINE_FUTURE_SESSIONS = [{'date': '2026-01-13',
  'type': 'TEST',
  'prescribed_sets': [{'reps': 8, 'weight_kg': 8.5, 'rest_s': 240}]},
 {'date': '2026-01-16',
  'type': 'H',
  'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]},
 {'date': '2026-01-20',
  'type': 'S',
  'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                      {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]},
 {'date': '2026-01-23',
  'type': 'H',
  'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]},
 {'date': '2026-01-27',
  'type': 'S',
  'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                      {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]},
 {'date': '2026-01-30',
  'type': 'H',
  'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]},
 {'date': '2026-02-03',
  'type': 'S',
  'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                      {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]},
 {'date': '2026-02-06',
  'type': 'H',
  'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                      {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]}]
P1_BSS_FUTURE_SESSIONS = [{'date': '2026-01-13',
  'type': 'TEST',
  'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 240}]},
 {'date': '2026-01-15',
  'type': 'S',
  'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 195}]},
 {'date': '2026-01-17',
  'type': 'H',
  'prescribed_sets': [{'reps': 9, 'weight_kg': 12.0, 'rest_s': 120},
                      {'reps': 8, 'weight_kg': 12.0, 'rest_s': 120}]},
 {'date': '2026-01-20',
  'type': 'E',
  'prescribed_sets': [{'reps': 10, 'weight_kg': 12.0, 'rest_s': 75},
                      {'reps': 10, 'weight_kg': 12.0, 'rest_s': 75}]},
 {'date': '2026-01-22',
  'type': 'S',
  'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 195}]},
 {'date': '2026-01-24',
  'type': 'H',
  'prescribed_sets': [{'reps': 9, 'weight_kg': 12.0, 'rest_s': 120},
                      {'reps': 8, 'weight_kg': 12.0, 'rest_s': 120}]},
 {'date': '2026-01-27',
  'type': 'E',
  'prescribed_sets': [{'reps': 10, 'weight_kg': 12.0, 'rest_s': 75},
                      {'reps': 10, 'weight_kg': 12.0, 'rest_s': 75}]},
 {'date': '2026-01-29',
  'type': 'S',
  'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 195}]},
 {'date': '2026-01-31',
  'type': 'H',
  'prescribed_sets': [{'reps': 9, 'weight_kg': 12.0, 'rest_s': 120},
                      {'reps': 8, 'weight_kg': 12.0, 'rest_s': 120}]},
 {'date': '2026-02-03',
  'type': 'E',
  'prescribed_sets': [{'reps': 10, 'weight_kg': 12.0, 'rest_s': 75},
                      {'reps': 10, 'weight_kg': 12.0, 'rest_s': 75}]},
 {'date': '2026-02-05',
  'type': 'S',
  'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 195}]},
 {'date': '2026-02-07',
  'type': 'H',
  'prescribed_sets': [{'reps': 9, 'weight_kg': 12.0, 'rest_s': 120},
                      {'reps': 8, 'weight_kg': 12.0, 'rest_s': 120}]}]

# --- Layer 2: done-session metrics ---
P1_DIP_DONE_METRICS = [{'volume_session': 78.0, 'avg_volume_set': 78.0, 'estimated_1rm': 27.7},
 {'volume_session': 234.0, 'avg_volume_set': 78.0, 'estimated_1rm': 27.7},
 {'volume_session': 234.0, 'avg_volume_set': 78.0, 'estimated_1rm': 27.7},
 {'volume_session': 390.0, 'avg_volume_set': 78.0, 'estimated_1rm': 27.7},
 {'volume_session': 156.0, 'avg_volume_set': 52.0, 'estimated_1rm': 26.92},
 {'volume_session': 312.0, 'avg_volume_set': 104.0, 'estimated_1rm': 28.53},
 {'volume_session': 312.0, 'avg_volume_set': 104.0, 'estimated_1rm': 28.53},
 {'volume_session': 312.0, 'avg_volume_set': 78.0, 'estimated_1rm': 27.7},
 {'volume_session': 156.0, 'avg_volume_set': 52.0, 'estimated_1rm': 26.92},
 {'volume_session': 312.0, 'avg_volume_set': 104.0, 'estimated_1rm': 28.53}]
P1_INCLINE_DONE_METRICS = [{'volume_session': 32.0, 'avg_volume_set': 32.0, 'estimated_1rm': 5.01},
 {'volume_session': 128.0, 'avg_volume_set': 32.0, 'estimated_1rm': 5.01},
 {'volume_session': 110.0, 'avg_volume_set': 27.5, 'estimated_1rm': 6.22},
 {'volume_session': 176.0, 'avg_volume_set': 44.0, 'estimated_1rm': 6.89},
 {'volume_session': 110.0, 'avg_volume_set': 27.5, 'estimated_1rm': 6.22},
 {'volume_session': 240.0, 'avg_volume_set': 48.0, 'estimated_1rm': 5.36},
 {'volume_session': 140.0, 'avg_volume_set': 35.0, 'estimated_1rm': 7.92},
 {'volume_session': 224.0, 'avg_volume_set': 56.0, 'estimated_1rm': 8.77},
 {'volume_session': 170.0, 'avg_volume_set': 42.5, 'estimated_1rm': 9.61},
 {'volume_session': 272.0, 'avg_volume_set': 68.0, 'estimated_1rm': 10.65}]
P1_BSS_DONE_METRICS = [{'volume_session': 237.5, 'avg_volume_set': 237.5, 'estimated_1rm': 53.73},
 {'volume_session': 1425.0, 'avg_volume_set': 475.0, 'estimated_1rm': 63.46},
 {'volume_session': 950.0, 'avg_volume_set': 237.5, 'estimated_1rm': 53.73},
 {'volume_session': 2730.0, 'avg_volume_set': 682.5, 'estimated_1rm': 63.95},
 {'volume_session': 1425.0, 'avg_volume_set': 475.0, 'estimated_1rm': 63.46},
 {'volume_session': 990.0, 'avg_volume_set': 247.5, 'estimated_1rm': 55.99},
 {'volume_session': 1485.0, 'avg_volume_set': 495.0, 'estimated_1rm': 66.13},
 {'volume_session': 2850.0, 'avg_volume_set': 712.5, 'estimated_1rm': 66.76},
 {'volume_session': 990.0, 'avg_volume_set': 247.5, 'estimated_1rm': 55.99},
 {'volume_session': 1485.0, 'avg_volume_set': 495.0, 'estimated_1rm': 66.13}]

# --- Layer 3: plan state after improved TEST ---
P1_DIP_AFTER_IMPROVED_TEST = {'status': {'training_max': 5,
            'latest_test_max': 6,
            'trend_slope_per_week': 0.0,
            'is_plateau': False,
            'deload_recommended': True,
            'readiness_z_score': 0.6539,
            'fitness': 7.6456,
            'fatigue': 4.0774},
 'future_sessions': [{'date': '2026-01-13',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 3, 'weight_kg': 0.0, 'rest_s': 240}]},
                     {'date': '2026-01-20',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 3, 'weight_kg': 0.0, 'rest_s': 240}]},
                     {'date': '2026-01-27',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 3, 'weight_kg': 0.0, 'rest_s': 240}]},
                     {'date': '2026-02-03',
                      'type': 'TEST',
                      'prescribed_sets': [{'reps': 7, 'weight_kg': 0.0, 'rest_s': 240}]}]}
P1_INCLINE_AFTER_IMPROVED_TEST = {'status': {'training_max': 10,
            'latest_test_max': 12,
            'trend_slope_per_week': 0.0,
            'is_plateau': False,
            'deload_recommended': True,
            'readiness_z_score': 0.6882,
            'fitness': 37.1492,
            'fatigue': 19.5368},
 'future_sessions': [{'date': '2026-01-13',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                                          {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240},
                                          {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]},
                     {'date': '2026-01-16',
                      'type': 'H',
                      'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]},
                     {'date': '2026-01-20',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                                          {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240},
                                          {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]},
                     {'date': '2026-01-23',
                      'type': 'H',
                      'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]}]}
P1_BSS_AFTER_IMPROVED_TEST = {'status': {'training_max': 7,
            'latest_test_max': 8,
            'trend_slope_per_week': 0.0,
            'is_plateau': False,
            'deload_recommended': True,
            'readiness_z_score': 1.1063,
            'fitness': 39.6515,
            'fatigue': 16.8019},
 'future_sessions': [{'date': '2026-01-13',
                      'type': 'E',
                      'prescribed_sets': [{'reps': 10, 'weight_kg': 14.0, 'rest_s': 75},
                                          {'reps': 10, 'weight_kg': 14.0, 'rest_s': 75},
                                          {'reps': 10, 'weight_kg': 14.0, 'rest_s': 75}]},
                     {'date': '2026-01-15',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 5, 'weight_kg': 14.0, 'rest_s': 195},
                                          {'reps': 4, 'weight_kg': 14.0, 'rest_s': 195}]},
                     {'date': '2026-01-17',
                      'type': 'H',
                      'prescribed_sets': [{'reps': 9, 'weight_kg': 14.0, 'rest_s': 120},
                                          {'reps': 8, 'weight_kg': 14.0, 'rest_s': 120},
                                          {'reps': 7, 'weight_kg': 14.0, 'rest_s': 120}]},
                     {'date': '2026-01-20',
                      'type': 'E',
                      'prescribed_sets': [{'reps': 10, 'weight_kg': 14.0, 'rest_s': 75},
                                          {'reps': 10, 'weight_kg': 14.0, 'rest_s': 75},
                                          {'reps': 10, 'weight_kg': 14.0, 'rest_s': 75}]}]}

# --- Layer 4: expected plan state after overperformance session ---
P1_INCLINE_AFTER_OVERPERFORMANCE = {'status': {'training_max': 7,
            'latest_test_max': 8,
            'trend_slope_per_week': 0.0,
            'is_plateau': False,
            'deload_recommended': False,
            'readiness_z_score': 0.0408,
            'fitness': 46.9567,
            'fatigue': 41.6969},
 'future_sessions': [{'date': '2026-01-16',
                      'type': 'H',
                      'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]},
                     {'date': '2026-01-20',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                                          {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]},
                     {'date': '2026-01-23',
                      'type': 'H',
                      'prescribed_sets': [{'reps': 7, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 6, 'weight_kg': 7.0, 'rest_s': 120},
                                          {'reps': 5, 'weight_kg': 7.0, 'rest_s': 120}]},
                     {'date': '2026-01-27',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 4, 'weight_kg': 7.0, 'rest_s': 240},
                                          {'reps': 3, 'weight_kg': 7.0, 'rest_s': 240}]}]}
P1_BSS_AFTER_OVERPERFORMANCE = {'status': {'training_max': 4,
            'latest_test_max': 5,
            'trend_slope_per_week': 0.0,
            'is_plateau': False,
            'deload_recommended': False,
            'readiness_z_score': 0.3393,
            'fitness': 54.7795,
            'fatigue': 49.9638},
 'future_sessions': [{'date': '2026-01-15',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 195}]},
                     {'date': '2026-01-17',
                      'type': 'H',
                      'prescribed_sets': [{'reps': 9, 'weight_kg': 12.0, 'rest_s': 120},
                                          {'reps': 8, 'weight_kg': 12.0, 'rest_s': 120}]},
                     {'date': '2026-01-20',
                      'type': 'E',
                      'prescribed_sets': [{'reps': 10, 'weight_kg': 12.0, 'rest_s': 75},
                                          {'reps': 10, 'weight_kg': 12.0, 'rest_s': 75}]},
                     {'date': '2026-01-22',
                      'type': 'S',
                      'prescribed_sets': [{'reps': 5, 'weight_kg': 12.0, 'rest_s': 195}]}]}

# --- Layer 5: 15W checkpoints ---
P1_INCLINE_15W_CHECKPOINTS = {7: {'is_plateau': False,
     'deload_recommended': True,
     'readiness_z_score': 2.201,
     'readiness_z_score_min': 1.701,
     'readiness_z_score_max': 2.701},
 14: {'is_plateau': False,
      'deload_recommended': True,
      'readiness_z_score': 2.6203,
      'readiness_z_score_min': 2.0962,
      'readiness_z_score_max': 3.1444},
 20: {'is_plateau': False,
      'deload_recommended': True,
      'readiness_z_score': 0.7309,
      'readiness_z_score_min': 0.2309,
      'readiness_z_score_max': 1.2309}}
