"""Compact plan-style sets parser: ``[groups] [+Wkg] [/ Rs]``.

A group is ``NxM`` (M sets of N reps) or a bare ``N`` (one set). All sets in a
compact expression share one weight and rest. Returns ``None`` when the string
is not in compact form so the per-set parser can take over.
"""

import re

from bar_scheduler.domain.results import ParsedSet

_DEFAULT_REST_SECONDS = 180

_REST_SUFFIX = re.compile(r"\s*/\s*(\d+)\s*s\s*$")
_WEIGHT_SUFFIX = re.compile(r"\+\s*([0-9]+(?:\.[0-9]+)?)\s*kg\s*$", re.IGNORECASE)
_NxM = re.compile(r"(\d+)\s*[xX×]\s*(\d+)")
_BARE = re.compile(r"(\d+)")


def _is_compact(text: str) -> bool:
    """Compact requires an 'x'/'×' multiplier or a trailing ``/ Ns`` rest."""
    has_multiplier = bool(re.search(r"[xX×]", text))
    has_rest_suffix = bool(re.search(r"/\s*\d+\s*s\s*$", text))
    return has_multiplier or has_rest_suffix


def _strip_rest(text: str) -> tuple[str, int]:
    match = _REST_SUFFIX.search(text)
    if not match:
        return text, _DEFAULT_REST_SECONDS
    head = text[: match.start()].strip()
    return head, int(match.group(1))


def _strip_weight(text: str) -> tuple[str, float]:
    match = _WEIGHT_SUFFIX.search(text)
    if not match:
        return text, 0.0
    head = text[: match.start()].strip()
    return head, float(match.group(1))


def _expand_group(group: str, weight: float, rest: int) -> list[ParsedSet] | None:
    """Expand one group into sets, or None if it is not a valid group."""
    nxm = _NxM.fullmatch(group)
    if nxm:
        n_reps = int(nxm.group(1))
        n_sets = int(nxm.group(2))
        if n_sets < 1 or n_reps < 0:
            return None
        return [ParsedSet(n_reps, weight, rest) for _ in range(n_sets)]
    bare = _BARE.fullmatch(group)
    if bare:
        return [ParsedSet(int(bare.group(1)), weight, rest)]
    return None


def _parse_groups(text: str, weight: float, rest: int) -> list[ParsedSet] | None:
    groups = [token.strip() for token in text.split(",") if token.strip()]
    parsed: list[ParsedSet] = []
    for group in groups:
        expanded = _expand_group(group, weight, rest)
        if expanded is None:
            return None
        parsed.extend(expanded)
    return parsed or None


def parse_compact_sets(sets_str: str) -> list[ParsedSet] | None:
    """Parse a compact sets string, or return None if it is not compact form.

    Examples: ``"5x4"`` -> 4×5 reps; ``"5x4 +0.5kg / 240s"`` -> 4×5 @ +0.5 kg,
    240 s; ``"4, 3x8 / 60s"`` -> 1×4 + 8×3 reps, 60 s.
    """
    text = sets_str.strip()
    if not _is_compact(text):
        return None
    text, rest = _strip_rest(text)
    text, weight = _strip_weight(text)
    return _parse_groups(text, weight, rest)
