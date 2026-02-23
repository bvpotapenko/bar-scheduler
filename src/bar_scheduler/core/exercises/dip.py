"""
Parallel Bar Dip exercise definition.

Biomechanics note
-----------------
Approximately 91–92% of bodyweight is lifted during bar dips (bw_fraction=0.92).
The hands and forearms (~5% BW) are fixed to the bars and not displaced; upper
arms rotate rather than translate, reducing their effective contribution.  This
matches published biomechanical approximations (~91.5% BW for bar dips).

Source: McKenzie et al. (2022). Bench, Bar, and Ring Dips: Kinematics and Muscle
Activity. PMCID: PMC9603242.
"""

from .base import ExerciseDefinition, SessionTypeParams

DIP = ExerciseDefinition(
    exercise_id="dip",
    display_name="Parallel Bar Dip",
    muscle_group="upper_push",

    bw_fraction=0.92,
    load_type="bw_plus_external",

    variants=["standard", "chest_lean", "tricep_upright"],
    primary_variant="standard",
    variant_factors={
        "standard": 1.00,
        "chest_lean": 0.97,       # slightly easier due to pec recruitment
        "tricep_upright": 1.03,   # harder for triceps
    },

    grip_cycles={
        "S": ["standard", "chest_lean", "tricep_upright"],
        "H": ["standard", "chest_lean", "tricep_upright"],
        "T": ["standard", "tricep_upright"],
        "E": ["standard"],
        "TEST": ["standard"],
    },

    session_params={
        "S": SessionTypeParams(
            reps_fraction_low=0.35,
            reps_fraction_high=0.55,
            reps_min=3,
            reps_max=8,
            sets_min=3,
            sets_max=5,
            rest_min=180,
            rest_max=300,
            rir_target=2,
        ),
        "H": SessionTypeParams(
            reps_fraction_low=0.55,
            reps_fraction_high=0.75,
            reps_min=6,
            reps_max=15,
            sets_min=4,
            sets_max=6,
            rest_min=120,
            rest_max=180,
            rir_target=2,
        ),
        "E": SessionTypeParams(
            reps_fraction_low=0.35,
            reps_fraction_high=0.55,
            reps_min=3,
            reps_max=10,
            sets_min=5,
            sets_max=8,
            rest_min=45,
            rest_max=90,
            rir_target=3,
        ),
        "T": SessionTypeParams(
            reps_fraction_low=0.20,
            reps_fraction_high=0.40,
            reps_min=2,
            reps_max=5,
            sets_min=4,
            sets_max=8,
            rest_min=60,
            rest_max=120,
            rir_target=5,
        ),
        "TEST": SessionTypeParams(
            reps_fraction_low=1.0,
            reps_fraction_high=1.0,
            reps_min=1,
            reps_max=80,
            sets_min=1,
            sets_max=1,
            rest_min=180,
            rest_max=300,
            rir_target=0,
        ),
    },

    target_metric="max_reps",
    target_value=40.0,

    test_protocol=(
        "DIP MAX REP TEST\n"
        "Warm-up: 2 min arm swings, 10 light push-ups, 1 set of 5 easy dips, rest 2 min.\n"
        "Test: arms locked out at top, lower until upper arm parallel to floor, press to lockout. "
        "No bouncing. Count clean reps only.\n"
        "Log as: --exercise dip --session-type TEST --sets 'N@0/180'"
    ),
    test_frequency_weeks=3,

    onerm_includes_bodyweight=True,
    onerm_explanation=(
        "Your dip 1RM includes your bodyweight (×0.92 BW fraction). "
        "If you weigh 82 kg and do 1 dip with +30 kg, effective load = 0.92×82 + 30 = 105.4 kg. "
        "Formula: 1RM = (BW×0.92 + added_weight) × (1 + reps/30)  [Epley]."
    ),

    weight_increment_fraction=0.012,  # 1.2% of effective BW per TM point above threshold
    weight_tm_threshold=12,
    max_added_weight_kg=30.0,
)
