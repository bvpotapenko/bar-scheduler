"""
Pull-Up exercise definition.

Refactors pull-up-specific constants that previously lived in config.py.

Biomechanics note
-----------------
Near-100% of bodyweight is displaced during a strict pull-up (bw_fraction=1.0).
Hands and forearms are fixed to the bar and move with the body; upper-arm
rotation contributes to vertical displacement.  A small correction for distal
forearm mass (~2–3%) is ignored for practical purposes.
"""

from .base import ExerciseDefinition, SessionTypeParams

PULL_UP = ExerciseDefinition(
    exercise_id="pull_up",
    display_name="Pull-Up",
    muscle_group="upper_pull",

    bw_fraction=1.0,
    load_type="bw_plus_external",

    variants=["pronated", "neutral", "supinated"],
    primary_variant="pronated",
    variant_factors={
        "pronated": 1.00,
        "neutral": 1.00,
        "supinated": 1.00,
    },

    # Grip rotation: S and H cycle through all three; T uses two; E/TEST fixed pronated.
    grip_cycles={
        "S": ["pronated", "neutral", "supinated"],
        "H": ["pronated", "neutral", "supinated"],
        "T": ["pronated", "neutral"],
        "E": ["pronated"],
        "TEST": ["pronated"],
    },

    session_params={
        "S": SessionTypeParams(
            reps_fraction_low=0.35,
            reps_fraction_high=0.55,
            reps_min=4,
            reps_max=6,
            sets_min=4,
            sets_max=5,
            rest_min=180,
            rest_max=300,
            rir_target=2,
        ),
        "H": SessionTypeParams(
            reps_fraction_low=0.60,
            reps_fraction_high=0.85,
            reps_min=6,
            reps_max=12,
            sets_min=4,
            sets_max=6,
            rest_min=120,
            rest_max=180,
            rir_target=2,
        ),
        "E": SessionTypeParams(
            reps_fraction_low=0.40,
            reps_fraction_high=0.60,
            reps_min=3,
            reps_max=8,
            sets_min=6,
            sets_max=10,
            rest_min=45,
            rest_max=75,
            rir_target=3,
        ),
        "T": SessionTypeParams(
            reps_fraction_low=0.20,
            reps_fraction_high=0.40,
            reps_min=2,
            reps_max=4,
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
            reps_max=50,
            sets_min=1,
            sets_max=1,
            rest_min=180,
            rest_max=300,
            rir_target=0,
        ),
    },

    target_metric="max_reps",
    target_value=30.0,

    test_protocol=(
        "PULL-UP MAX REP TEST\n"
        "Warm-up: 2 min arm circles, 1 set of 5 easy pull-ups, rest 2 min.\n"
        "Test: dead hang, pronated grip, shoulder-width. Pull until chin over bar. "
        "Lower to full extension each rep. No kipping. Count clean reps only.\n"
        "Log as: --session-type TEST --sets 'N@0/180'"
    ),
    test_frequency_weeks=3,

    onerm_includes_bodyweight=True,
    onerm_explanation=(
        "Your pull-up 1RM includes your bodyweight. "
        "If you weigh 82 kg and do 1 pull-up with +20 kg added, your 1RM is 102 kg. "
        "Formula: 1RM = (BW + added_weight) × (1 + reps/30)  [Epley]."
    ),

    weight_increment_fraction=0.01,   # 1% of BW per TM point above threshold
    weight_tm_threshold=9,
    max_added_weight_kg=20.0,
)
