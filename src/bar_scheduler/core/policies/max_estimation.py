"""Track B between-test max estimator (FI + Nuzzo methods).

FI method (Pekunlu & Atalag 2013): fatigue index FI = 1 - mean(R2..Rn)/R1,
corrected for incomplete PCr recovery (Bogdanis 1995).
Nuzzo method (2024): invert a reps~%1RM table to recover the fresh single-set max.
"""

from bar_scheduler.core.math.nuzzo import fi_max_estimate, nuzzo_max_estimate
from bar_scheduler.domain.results import MaxEstimate

_Valid = tuple[int, int, int | None]  # (reps, rest, rir)
IntList = list[int]
RirList = list[int | None]
_DEFAULT_REST_SECONDS = 180


def _padded(seq: list, length: int, default) -> list:
    """Pad ``seq`` to ``length`` with ``default`` (longer sequences truncated by zip)."""
    pad = [default for _ in range(length - len(seq))]
    return list(seq) + pad


def _valid_sets(reps_per_set: IntList, rests: IntList, rirs: RirList) -> list[_Valid]:
    """(reps, rest, rir) for sets with reps > 0; defaults rest 180, rir None."""
    count = len(reps_per_set)
    padded_rests = _padded(rests, count, _DEFAULT_REST_SECONDS)
    padded_rirs = _padded(rirs, count, None)
    rows = zip(reps_per_set, padded_rests, padded_rirs)
    return [row for row in rows if row[0] > 0]


def _fatigue_index(reps: IntList) -> float:
    """FI = 1 - mean(R2..Rn) / R1, clamped to [0, 1]."""
    first = reps[0]
    if first <= 0:
        return 0.0
    subsequent = reps[1:]
    fi_reps = 1.0 - (sum(subsequent) / len(subsequent)) / first
    return max(0.0, min(1.0, fi_reps))


def _confidence(n_sets: int, rir_known: bool) -> str:
    if n_sets >= 4 and rir_known:
        return "high"
    if n_sets >= 2:
        return "medium"
    return "low"


class MaxEstimator:
    """Estimate fresh max reps from a multi-set training session (Track B)."""

    def estimate(
        self,
        reps_per_set: list[int],
        rests: list[int],
        rirs: list[int | None] | None = None,
    ) -> MaxEstimate | None:
        """Return a MaxEstimate, or None if fewer than 2 sets had reps > 0."""
        valid = _valid_sets(reps_per_set, rests, rirs or [])
        if len(valid) < 2:
            return None
        reps = [entry[0] for entry in valid]
        fi_reps = _fatigue_index(reps)
        rir_known = rirs is not None and any(rir is not None for rir in rirs)
        return MaxEstimate(
            fi_est=fi_max_estimate(reps[0], valid[0][1], fi_reps),
            nuzzo_est=nuzzo_max_estimate(reps[0], [entry[2] for entry in valid], fi_reps),
            fi_reps=round(fi_reps, 3),
            confidence=_confidence(len(reps), rir_known),
        )
