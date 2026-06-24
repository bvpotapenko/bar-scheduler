"""Read-only exercise catalog/metadata functions for the bar-scheduler API."""

from __future__ import annotations

from dataclasses import asdict

from bar_scheduler.core.exercises.registry import all_exercises, get_exercise


def _exercise_to_dict(ex) -> dict:
    """Public metadata for one exercise definition (shared shape)."""
    return {
        "display_name": ex.display_name,
        "muscle_group": ex.muscle_group,
        "variants": list(ex.variants),
        "primary_variant": ex.primary_variant,
        "has_variant_rotation": ex.has_variant_rotation,
        "bw_fraction": ex.bw_fraction,
        "onerm_includes_bodyweight": ex.onerm_includes_bodyweight,
        "session_params": {stype: asdict(sp) for stype, sp in ex.session_params.items()},
        "onerm_explanation": ex.onerm_explanation,
        "default_item": ex.default_item,
    }


def list_exercises() -> dict[str, dict]:
    """Return public metadata for all registered exercises, keyed by ID."""
    return {ex.exercise_id: _exercise_to_dict(ex) for ex in all_exercises()}


def get_exercise_info(exercise_id: str) -> dict:
    """Return public metadata for one exercise (same keys as list, plus ``id``).

    Raises ``ValueError`` for unknown IDs.
    """
    ex = get_exercise(exercise_id)
    return {"id": ex.exercise_id, **_exercise_to_dict(ex)}


def get_equipment_catalog(exercise_id: str) -> dict:
    """Return the equipment catalog for an exercise.

    Keys: ``default_item`` (item ID to pre-select; empty string if undefined)
    and ``items`` (dict keyed by item ID with ``label``, ``assistance_kg``,
    ``requires_weight_declaration``). Unknown IDs return empty defaults.
    """
    try:
        ex = get_exercise(exercise_id)
    except ValueError:
        return {"default_item": "", "items": {}}
    return {
        "default_item": ex.default_item,
        "items": {item_id: dict(item_cfg) for item_id, item_cfg in ex.equipment.items()},
    }
