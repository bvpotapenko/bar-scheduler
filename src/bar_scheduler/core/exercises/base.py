"""
Base types for exercise definitions.

ExerciseDefinition parameterises the shared planning engine for any
exercise the planner can manage. SessionTypeParams holds per-session-type
configuration (reps, sets, rest, RIR) tuned for the specific exercise.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SessionTypeParams:
    """Parameters for one session type within an exercise."""

    reps_fraction_low: float   # Lower bound as fraction of TM
    reps_fraction_high: float  # Upper bound as fraction of TM
    reps_min: int              # Absolute minimum reps per set
    reps_max: int              # Absolute maximum reps per set
    sets_min: int
    sets_max: int
    rest_min: int              # Rest in seconds
    rest_max: int
    rir_target: int            # Reps-in-reserve target


@dataclass(frozen=True)
class ExerciseDefinition:
    """
    Full configuration for one exercise.

    Passed to the planning engine to parameterise grip rotation, session
    type parameters, added-weight formula, 1RM calculation, and assessment.
    """

    # Identity
    exercise_id: str          # e.g. "pull_up", "dip", "bss"
    display_name: str         # e.g. "Pull-Up"
    muscle_group: str         # e.g. "upper_pull"

    # Load model
    bw_fraction: float        # Fraction of BW that is the working load (1.0=pull-up, 0.0=BSS)
    load_type: str            # "bw_plus_external" | "external_only"

    # Movement variants (analogous to "grips" for pull-ups)
    variants: list[str]
    primary_variant: str      # Used for standardised testing
    variant_factors: dict[str, float]  # Normalisation factor per variant

    # Session type configurations
    session_params: dict[str, SessionTypeParams]

    # Goal
    target_metric: str        # "max_reps" | "1rm_kg"
    target_value: float       # e.g. 30 reps, 120 kg

    # Assessment
    test_protocol: str        # Human-readable test instructions
    test_frequency_weeks: int # Recommended interval between tests

    # 1RM display
    onerm_includes_bodyweight: bool
    onerm_explanation: str

    # Added-weight formula
    weight_increment_fraction: float  # Fraction of effective load per TM point above threshold
    weight_tm_threshold: int          # TM must exceed this before adding weight
    max_added_weight_kg: float        # Absolute cap on added weight

    # Whether to rotate through variants across sessions.
    # False = always use primary_variant (e.g. dips where varying lean is undesirable).
    has_variant_rotation: bool = True

    # Grip/variant rotation per session type (only used when has_variant_rotation=True)
    grip_cycles: dict[str, list[str]] = field(default_factory=dict)
