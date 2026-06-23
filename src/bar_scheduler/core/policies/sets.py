"""Set and rep prescription per session type (sets, reps, rest, added weight)."""

from dataclasses import dataclass

from bar_scheduler.core.exercises.base import ExerciseDefinition, SessionTypeParams
from bar_scheduler.core.policies.autoregulation import AutoregulationPolicy
from bar_scheduler.core.policies.load import LoadCalculator
from bar_scheduler.core.policies.rest import RestAdvisor
from bar_scheduler.domain.context import AdaptationSignals, PrescriptionContext
from bar_scheduler.domain.models import PlannedSet

_Volume = tuple[int, int, int]  # (adj_sets, adj_reps, target_reps)


@dataclass(frozen=True)
class _SetShape:
    rest: int
    added: float
    rir_target: int
    reps_min: int


def _rep_targets(training_max: int, sparams: SessionTypeParams) -> int:
    """Mid-range target reps from TM and session params, clamped to [min, max]."""
    reps_low = max(sparams.reps_min, int(training_max * sparams.reps_fraction_low))
    reps_high = min(sparams.reps_max, int(training_max * sparams.reps_fraction_high))
    target = (reps_low + reps_high) // 2
    return max(sparams.reps_min, min(sparams.reps_max, target))


def _classify_level(latest_test_max: int | None, level_thresholds: list[int] | None) -> int:
    """First level index whose threshold >= test max (middle level when unknown)."""
    if latest_test_max is None or not level_thresholds:
        num_levels = len(level_thresholds) if level_thresholds else 2
        return max(0, (num_levels - 1) // 2)
    for idx, threshold in enumerate(level_thresholds):
        if latest_test_max <= threshold:
            return idx
    return len(level_thresholds)


def _base_sets(exercise: ExerciseDefinition, sparams: SessionTypeParams, latest_test_max: int | None) -> int:
    """Level-based set count, or the mid-range count when levels are undefined."""
    levels = sparams.sets_by_level
    if levels is not None and exercise.level_thresholds is not None:
        level = _classify_level(latest_test_max, exercise.level_thresholds)
        idx = min(level, len(levels) - 1)
        return levels[idx]
    return (sparams.sets_min + sparams.sets_max) // 2


def _build_decayed_sets(num_sets: int, reps: int, curve: list[float], shape: _SetShape) -> list[PlannedSet]:
    """S/H/T/TEST: per-set rep decay following the exercise fatigue curve."""
    out: list[PlannedSet] = []
    for idx in range(num_sets):
        factor = curve[-1]
        if idx < len(curve):
            factor = curve[idx]
        out.append(PlannedSet(
            target_reps=max(1, round(reps * factor)),
            rest_seconds_before=shape.rest,
            added_weight_kg=shape.added,
            rir_target=shape.rir_target,
        ))
    return out


def _build_endurance_sets(num_sets: int, target_reps: int, shape: _SetShape) -> list[PlannedSet]:
    """Endurance: descending-ladder reps, floored at reps_min."""
    out: list[PlannedSet] = []
    current = target_reps
    for _slot in range(num_sets):
        out.append(PlannedSet(
            target_reps=max(shape.reps_min, current),
            rest_seconds_before=shape.rest,
            added_weight_kg=shape.added,
            rir_target=shape.rir_target,
        ))
        current = max(shape.reps_min, current - 1)
    return out


class SetPrescriptor:
    """Compose sets/reps/rest/weight for a session from the prescription policies."""

    def __init__(
        self,
        load: LoadCalculator,
        rest: RestAdvisor,
        autoreg: AutoregulationPolicy,
        tm_factor: float,
    ) -> None:
        self._load = load
        self._rest = rest
        self._autoreg = autoreg
        self._tm_factor = tm_factor

    def prescribe(self, ctx: PrescriptionContext, signals: AdaptationSignals) -> list[PlannedSet]:
        """Return the PlannedSet list for one session slot."""
        sparams = ctx.exercise.session_params[ctx.session_type]
        volume = self._volume(ctx, sparams, signals)
        rest = self._rest.recommend(
            ctx.session_type, list(signals.recent_same_type), signals.ff_state, ctx.exercise,
        )
        return self._build(ctx, sparams, volume, rest)

    def _target_reps(self, ctx: PrescriptionContext, sparams: SessionTypeParams, latest_test_max: int | None) -> int:
        if ctx.session_type != "TEST":
            return _rep_targets(ctx.training_max, sparams)
        if latest_test_max is None:
            return sparams.reps_max
        return round(ctx.training_max / self._tm_factor) + 1

    def _volume(self, ctx: PrescriptionContext, sparams: SessionTypeParams, signals: AdaptationSignals) -> _Volume:
        target_reps = self._target_reps(ctx, sparams, signals.latest_test_max)
        base = (_base_sets(ctx.exercise, sparams, signals.latest_test_max), target_reps)
        adj_sets, adj_reps = self._autoreg.adjust(
            base, signals.ff_state, signals.history_sessions, sparams.sets_min,
        )
        return adj_sets, adj_reps, target_reps

    def _build(self, ctx: PrescriptionContext, sparams: SessionTypeParams, volume: _Volume, rest: int) -> list[PlannedSet]:
        adj_sets, adj_reps, target_reps = volume
        shape = _SetShape(
            rest=rest,
            added=self._load.added_weight(ctx),
            rir_target=sparams.rir_target,
            reps_min=sparams.reps_min,
        )
        if ctx.session_type == "E":
            return _build_endurance_sets(adj_sets, target_reps, shape)
        return _build_decayed_sets(adj_sets, adj_reps, ctx.exercise.set_fatigue_curve, shape)
