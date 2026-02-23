"""
Bulgarian Split Squat (DB) exercise definition.

Biomechanics note
-----------------
BSS is a unilateral, hip-dominant exercise performed with dumbbells.
bw_fraction=0.0 because bodyweight is NOT included in the 1RM calculation:
the load is the dumbbell weight only, matching standard DB-exercise conventions.

Source: Mackey & Riemann (2021). Biomechanical Differences Between the Bulgarian
Split-Squat and Back Squat. Int J Exerc Sci, 14(1):533-543.
Song et al. (2023). Effects of step lengths on biomechanical characteristics in
split squat. Front Bioeng Biotechnol, 11:1277493.

Unilateral note
---------------
Each prescribed "set" means one set per leg.  The plan output appends "(per leg)"
to the prescription (handled in views.py).  The rest interval is between legs
(shorter, ~30–60 s) and between full rounds (the configured rest).

Weight progression
------------------
BSS uses external load (dumbbells) as the primary load.  weight_tm_threshold=999
means auto-weight-from-TM never triggers.  Instead, training sessions use the
dumbbell weight from the last logged TEST session as the prescribed weight.
"""

from .base import ExerciseDefinition, SessionTypeParams

BSS = ExerciseDefinition(
    exercise_id="bss",
    display_name="Bulgarian Split Squat (DB)",
    muscle_group="lower",

    bw_fraction=0.0,
    load_type="external_only",

    variants=["standard", "deficit", "front_foot_elevated"],
    primary_variant="standard",
    variant_factors={
        "standard": 1.00,
        "deficit": 1.05,             # harder ROM
        "front_foot_elevated": 0.95, # slightly easier
    },

    grip_cycles={
        "S": ["standard", "deficit", "front_foot_elevated"],
        "H": ["standard", "deficit", "front_foot_elevated"],
        "T": ["standard", "deficit"],
        "E": ["standard"],
        "TEST": ["standard"],
    },

    session_params={
        "S": SessionTypeParams(
            reps_fraction_low=0.50,
            reps_fraction_high=0.70,
            reps_min=4,
            reps_max=8,
            sets_min=3,
            sets_max=4,
            rest_min=150,
            rest_max=240,
            rir_target=2,
        ),
        "H": SessionTypeParams(
            reps_fraction_low=0.60,
            reps_fraction_high=0.80,
            reps_min=8,
            reps_max=15,
            sets_min=3,
            sets_max=5,
            rest_min=90,
            rest_max=150,
            rir_target=2,
        ),
        "E": SessionTypeParams(
            reps_fraction_low=0.40,
            reps_fraction_high=0.60,
            reps_min=10,
            reps_max=20,
            sets_min=3,
            sets_max=5,
            rest_min=60,
            rest_max=90,
            rir_target=3,
        ),
        "T": SessionTypeParams(
            reps_fraction_low=0.30,
            reps_fraction_high=0.50,
            reps_min=5,
            reps_max=10,
            sets_min=2,
            sets_max=4,
            rest_min=60,
            rest_max=120,
            rir_target=4,
        ),
        "TEST": SessionTypeParams(
            reps_fraction_low=1.0,
            reps_fraction_high=1.0,
            reps_min=1,
            reps_max=30,
            sets_min=1,
            sets_max=1,
            rest_min=180,
            rest_max=300,
            rir_target=0,
        ),
    },

    target_metric="max_reps",
    target_value=20.0,  # 20 reps per leg with target DB weight

    test_protocol=(
        "BULGARIAN SPLIT SQUAT MAX REP TEST (per leg)\n"
        "Setup: bench height ~45-50 cm; rear foot on bench, laces down; "
        "front foot ~60-75 cm in front.\n"
        "Warm-up: 5 BW lunges per leg, 5 BSS per leg with ~50% test weight, rest 2 min.\n"
        "Test: lower until front thigh at or below parallel, drive to full extension. "
        "Maintain upright torso. Count clean reps. Rest 2-3 min, test other leg. "
        "Record the LOWER of the two legs as your score.\n"
        "Log as: --exercise bss --session-type TEST --sets 'N@<total_db_kg>/180'"
    ),
    test_frequency_weeks=4,

    onerm_includes_bodyweight=False,
    onerm_explanation=(
        "Your BSS 1RM is the dumbbell weight only (both hands combined). "
        "If you hold 2×30 kg dumbbells and do 1 rep, your 1RM is 60 kg. "
        "Bodyweight is NOT included. "
        "Formula: 1RM = total_dumbbell_weight × (1 + reps/30)  [Epley]."
    ),

    weight_increment_fraction=0.0,   # Not applicable; progression is in reps, not auto-added weight
    weight_tm_threshold=999,         # Never auto-adds weight
    max_added_weight_kg=72.0,        # 2 × 36 kg max DB
)
