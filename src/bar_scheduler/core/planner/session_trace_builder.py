"""Format _SessionTrace objects into Rich-markup explanation strings."""

import math as _math

from ..config import (
    DROP_OFF_THRESHOLD,
    MIN_SESSIONS_FOR_AUTOREG,
    READINESS_VOLUME_REDUCTION,
    READINESS_Z_HIGH,
    READINESS_Z_LOW,
    TM_FACTOR,
    endurance_volume_multiplier,
    expected_reps_per_week,
)
from .types import _SessionTrace


def _format_explain(trace: _SessionTrace, bodyweight_kg: float) -> str:
    """
    Format a _SessionTrace into a Rich-markup step-by-step explanation.

    Pure formatter: no computation, no side-effects.
    All values come from the trace built by _plan_core().
    """
    TYPE_NAMES = {
        "S": "Strength",
        "H": "Hypertrophy",
        "E": "Endurance",
        "T": "Technique",
        "TEST": "Max Test",
    }

    ex = trace.exercise
    params = trace.params
    session_type = trace.session_type
    type_name = TYPE_NAMES.get(session_type, session_type)
    rest_mid = (params.rest_min + params.rest_max) // 2
    rule = "─" * 54
    L: list[str] = []

    # Header
    L.append(
        f"[bold cyan]{type_name} ({session_type})"
        f"  ·  {trace.date_str}"
        f"  ·  Week {trace.week_num}[/bold cyan]"
    )
    L.append(rule)

    # OVERTRAINING SHIFT NOTICE
    if trace.overtraining_shift_days > 0:
        L.append(
            f"\n[yellow]⚠ Session shifted +{trace.overtraining_shift_days} day(s) "
            f"(overtraining level {trace.overtraining_level}/3 detected). "
            f"Original plan start was pushed forward to allow recovery.[/yellow]"
        )

    # SESSION TYPE
    L.append("\n[bold]SESSION TYPE[/bold]")
    L.append(
        f"  {trace.days_per_week}-day schedule template: "
        f"[cyan]{' → '.join(trace.schedule)}[/cyan] (repeating weekly)."
    )
    L.append(f"  Week {trace.week_num} → [magenta]{session_type}[/magenta].")

    # GRIP
    L.append(f"\n[bold]GRIP: {trace.grip}[/bold]")
    if ex.has_variant_rotation:
        cycle_str = " → ".join(trace.cycle)
        plan_count = trace.count_before - trace.hist_count
        L.append(
            f"  {session_type} sessions rotate: [cyan]{cycle_str}[/cyan]"
            f" ({len(trace.cycle)}-step cycle)."
        )
        L.append(f"  In history: {trace.hist_count} {session_type} session(s).")
        if plan_count > 0:
            L.append(
                f"  In this plan before {trace.date_str}: {plan_count} {session_type} session(s)."
            )
        L.append(f"  Total before this session: {trace.count_before}.")
        L.append(
            f"  {trace.count_before} mod {len(trace.cycle)}"
            f" = [bold]{trace.count_before % len(trace.cycle)}[/bold]"
            f" → [green]{trace.grip}[/green]."
        )
    else:
        L.append(f"  Always uses primary variant (no rotation for {ex.display_name}).")

    # TRAINING MAX
    L.append(f"\n[bold]TRAINING MAX: {trace.current_tm}[/bold]")
    test_sessions = [s for s in trace.history if s.session_type == "TEST"]
    if test_sessions:
        latest_test = max(test_sessions, key=lambda s: s.date)
        latest_max = max(
            (s.actual_reps for s in latest_test.completed_sets if s.actual_reps),
            default=0,
        )
        tm_from_test = int(TM_FACTOR * latest_max)
        L.append(f"  Latest TEST: {latest_max} reps on {latest_test.date}.")
        L.append(f"  Starting TM = floor({TM_FACTOR} × {latest_max}) = {tm_from_test}.")
    else:
        L.append(f"  Starting TM: {trace.initial_tm}.")
    if trace.weekly_log:
        L.append("  Progression by week:")
        for wk, prog, before, after in trace.weekly_log:
            L.append(
                f"    Week {wk}: TM {before:.2f} + {prog:.2f} = [bold]{after:.2f}[/bold]"
                f" (int = {int(after)})"
            )
    else:
        L.append("  No weekly progression yet (first week of plan).")
    L.append(
        f"  → TM for this session: int({trace.tm_float:.2f})"
        f" = [bold green]{trace.current_tm}[/bold green]."
    )

    # SETS
    L.append(f"\n[bold]SETS: {trace.adj_sets}[/bold]")
    L.append(
        f"  {session_type} config: sets [{params.sets_min}–{params.sets_max}]."
        f"  Base = ({params.sets_min}+{params.sets_max})//2 = {trace.base_sets}."
    )
    L.append(
        f"  How the range is used: the midpoint ({trace.base_sets}) is the operational target."
        f"  Autoregulation can only reduce sets (never push above midpoint)."
        f"  High readiness adds +1 rep/set rather than adding more sets."
    )
    L.append(
        f"  Readiness z-score: {trace.z_score:+.2f}"
        f"  (thresholds: low={READINESS_Z_LOW}, high=+{READINESS_Z_HIGH})."
    )
    if not trace.has_autoreg:
        L.append(
            f"  Autoregulation: [dim]off[/dim]"
            f" (need ≥ {MIN_SESSIONS_FOR_AUTOREG} sessions, have {trace.history_len})."
        )
    elif trace.z_score < READINESS_Z_LOW:
        L.append(
            f"  z < {READINESS_Z_LOW} → reduce by {int(READINESS_VOLUME_REDUCTION*100)}%:"
            f" max(3, {int(trace.base_sets*(1-READINESS_VOLUME_REDUCTION))})"
            f" = [bold]{trace.adj_sets}[/bold]."
        )
    elif trace.z_score > READINESS_Z_HIGH:
        L.append(f"  z > +{READINESS_Z_HIGH} → sets unchanged, +1 rep (see Reps).")
    else:
        L.append(f"  z in [{READINESS_Z_LOW}, +{READINESS_Z_HIGH}] → no change.")
    L.append(f"  → [bold green]{trace.adj_sets} sets[/bold green].")

    # REPS
    L.append(f"\n[bold]REPS PER SET: {trace.adj_reps}[/bold]")
    L.append(
        f"  {session_type} config:"
        f" fraction [{params.reps_fraction_low}–{params.reps_fraction_high}]"
        f" of TM, clamped to [{params.reps_min}–{params.reps_max}]."
    )
    L.append(
        f"  Low  = max({params.reps_min}, int({trace.current_tm} × {params.reps_fraction_low}))"
        f" = max({params.reps_min}, {int(trace.current_tm * params.reps_fraction_low)})"
        f" = {trace.reps_low}."
    )
    L.append(
        f"  High = min({params.reps_max}, int({trace.current_tm} × {params.reps_fraction_high}))"
        f" = min({params.reps_max}, {int(trace.current_tm * params.reps_fraction_high)})"
        f" = {trace.reps_high}."
    )
    L.append(
        f"  Target = ({trace.reps_low}+{trace.reps_high})//2"
        f" = {(trace.reps_low + trace.reps_high) // 2},"
        f" clamped to [{params.reps_min}–{params.reps_max}] → {trace.base_reps}."
    )
    if trace.has_autoreg and trace.z_score > READINESS_Z_HIGH:
        L.append(
            f"  High readiness (z={trace.z_score:+.2f} > +{READINESS_Z_HIGH})"
            f" → +1 rep → {trace.adj_reps}."
        )
    L.append(f"  → [bold green]{trace.adj_reps} reps/set[/bold green].")

    # WEIGHT (S) or VOLUME (E)
    if session_type == "S":
        L.append(f"\n[bold]ADDED WEIGHT: {trace.added_weight:.1f} kg[/bold]")
        thr = ex.weight_tm_threshold
        frac = ex.weight_increment_fraction
        bwf = ex.bw_fraction
        if ex.load_type == "external_only":
            L.append(
                f"  External-load exercise -- dumbbell weight from last TEST session"
                f" ({trace.last_test_weight:.1f} kg)."
            )
        elif trace.current_tm > thr:
            eff_bw = bodyweight_kg * bwf
            raw_w = eff_bw * frac * (trace.current_tm - thr)
            rounded = round(raw_w * 2) / 2
            L.append(
                f"  TM = {trace.current_tm} > {thr} → BW×{bwf}×{frac}×(TM−{thr})"
                f" = {eff_bw:.1f}×{frac}×{trace.current_tm - thr} = {raw_w:.2f} kg."
            )
            L.append(
                f"  Rounded to nearest 0.5 kg: {rounded:.1f} kg."
                f"  Cap at {ex.max_added_weight_kg:.0f} kg"
                f" → [bold green]{trace.added_weight:.1f} kg[/bold green]."
            )
        else:
            L.append(
                f"  TM = {trace.current_tm} ≤ {thr} → bodyweight only (0 kg added)."
            )
    elif session_type == "E":
        ke = endurance_volume_multiplier(trace.current_tm)
        total_target = int(ke * trace.current_tm)
        L.append("\n[bold]VOLUME (Endurance -- descending ladder)[/bold]")
        L.append(
            f"  kE(TM={trace.current_tm}) = 3.0 + 2.0"
            f" × clip(({trace.current_tm}-5)/25, 0, 1) = {ke:.2f}."
        )
        L.append(
            f"  Total target = kE × TM = {ke:.2f} × {trace.current_tm} = {total_target} reps."
        )
        L.append(
            f"  Starting at {trace.base_reps} reps/set, decreasing by 1 each set"
            f" (min {params.reps_min})."
        )
        L.append(
            f"  Stops when accumulated ≥ {total_target} reps"
            f" or {params.sets_max} sets reached."
        )

    # REST -- rebuild rest_adj_notes from trace.recent_same_type using the same
    # logic as calculate_adaptive_rest() so the display stays in sync.
    rest_adj_notes: list[str] = []
    same_type_sessions = trace.recent_same_type
    if same_type_sessions:
        last_same = same_type_sessions[-1]
        sets_done = [s for s in last_same.completed_sets if s.actual_reps is not None]
        if sets_done:
            rirs = [s.rir_reported for s in sets_done if s.rir_reported is not None]
            if rirs:
                if any(r <= 1 for r in rirs):
                    rest_adj_notes.append("RIR ≤ 1 in a set → +30 s")
                elif all(r >= 3 for r in rirs):
                    rest_adj_notes.append("all sets RIR ≥ 3 → −15 s")
            reps_done = [s.actual_reps for s in sets_done if s.actual_reps is not None]
            if len(reps_done) >= 2 and reps_done[0] > 0:
                drop = (reps_done[0] - reps_done[-1]) / reps_done[0]
                if drop > DROP_OFF_THRESHOLD:
                    rest_adj_notes.append(
                        f"drop-off {drop:.0%} > {int(DROP_OFF_THRESHOLD*100)}% → +15 s"
                    )
    if trace.ff_state is not None:
        readiness_val = trace.ff_state.fitness - trace.ff_state.fatigue
        readiness_var_val = max(trace.ff_state.readiness_var, 0.01)
        z_rest = (readiness_val - trace.ff_state.readiness_mean) / _math.sqrt(
            readiness_var_val
        )
        if z_rest < READINESS_Z_LOW:
            rest_adj_notes.append(
                f"readiness z={z_rest:+.2f} < {READINESS_Z_LOW} → +30 s"
            )
    # Rest-adherence signal
    actual_rests = [
        s.rest_seconds_before
        for session in same_type_sessions
        for s in session.completed_sets
        if s.rest_seconds_before > 0
    ]
    if len(actual_rests) >= 3:
        avg_actual = sum(actual_rests) / len(actual_rests)
        if avg_actual < params.rest_min * 0.85:
            rest_adj_notes.append(
                f"avg actual rest {avg_actual:.0f} s"
                f" < {params.rest_min}×0.85={params.rest_min * 0.85:.0f} s → −20 s"
            )
        elif avg_actual > params.rest_max * 1.10:
            rest_adj_notes.append(
                f"avg actual rest {avg_actual:.0f} s"
                f" > {params.rest_max}×1.10={params.rest_max * 1.10:.0f} s → +20 s"
            )

    L.append(f"\n[bold]REST: {trace.adj_rest} s[/bold]")
    L.append(
        f"  {session_type} config: rest [{params.rest_min}–{params.rest_max}] s."
        f"  Base = ({params.rest_min}+{params.rest_max})//2 = {rest_mid} s."
    )
    if same_type_sessions and rest_adj_notes:
        L.append(
            f"  Adjustments from last {session_type} session"
            f" ({same_type_sessions[-1].date}):"
        )
        for note in rest_adj_notes:
            L.append(f"    {note}")
        L.append(
            f"  Clamped to [{params.rest_min}–{params.rest_max}] s → {trace.adj_rest} s."
        )
    elif not same_type_sessions:
        L.append(f"  No previous {session_type} session found → using midpoint.")
    else:
        L.append(
            f"  No adjustments needed from last {session_type} session → midpoint unchanged."
        )
    L.append(f"  → [bold green]{trace.adj_rest} s[/bold green].")

    # EXPECTED TM AFTER
    next_week_prog = expected_reps_per_week(trace.current_tm, trace.user_target)
    next_week_tm = trace.tm_float + next_week_prog
    L.append(f"\n[bold]EXPECTED TM AFTER: {trace.expected_tm_after}[/bold]")
    L.append("  TM is updated once per calendar week boundary.")
    L.append(
        f"  Current TM (this week): int({trace.tm_float:.2f}) = {trace.current_tm}."
    )
    L.append(
        f"  Next week's TM ≈ {trace.tm_float:.2f} + {next_week_prog:.2f}"
        f" = {next_week_tm:.2f} → int = {int(next_week_tm)}."
    )
    L.append(
        f"  → [bold green]{trace.expected_tm_after}[/bold green]"
        f" (this week's TM, shown consistently for all sessions in week {trace.week_num})."
    )

    return "\n".join(L)
