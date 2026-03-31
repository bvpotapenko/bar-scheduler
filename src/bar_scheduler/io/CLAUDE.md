# io/ — persistence layer

## File layout

| File | Write mode | Owns |
|------|-----------|------|
| `profile.json` | Replace | User profile (one per data_dir) |
| `{exercise_id}_history.jsonl` | Append-only | Training session records |
| `{exercise_id}_equipment.jsonl` | Append-only | Equipment state history |
| `.plan_cache_{exercise_id}.json` | Replace | Last generated plan (for change detection) |

## Invariants

- **Append-only.** Never edit or delete lines in history or equipment JSONL files. Always append a new record. Editing past records breaks prescription stability.
- **serializers.py is the sole I/O boundary.** All JSON ↔ dataclass conversion happens here. No ad-hoc dict construction in API or core modules.
- **Date format: ISO 8601 (`YYYY-MM-DD`) everywhere.** serializers.py enforces and validates this. Don't bypass it with raw string formatting.
- **ValidationError propagates.** Raised by serializers on malformed input; the API layer lets it reach callers. Don't silently swallow it.

## Adding a new model field

1. Update both `dict_to_*()` and `*_to_dict()` in `serializers.py`
2. Add a round-trip test in `tests/test_api.py`
3. If the field is optional, handle missing keys gracefully in `dict_to_*()` (old files won't have it)
