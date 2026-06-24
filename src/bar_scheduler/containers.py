"""Composition root: wires the policy graph into application services.

A single app-wide container (policies are exercise-agnostic; the exercise flows
through ``PrescriptionContext`` at call time). API modules resolve services from
the module-level ``container``; tests override providers with fakes.
"""

from dependency_injector import containers, providers

from bar_scheduler.config import load_model_config
from bar_scheduler.core import policies, services


class Container(containers.DeclarativeContainer):
    """Provider graph: typed config -> policies -> services."""

    config = providers.Singleton(load_model_config)

    rest_advisor = providers.Singleton(
        policies.RestAdvisor,
        drop_off_threshold=config.provided.within_session_fatigue.DROP_OFF_THRESHOLD,
        readiness_z_low=config.provided.readiness.READINESS_Z_LOW,
    )
    load_calculator = providers.Singleton(
        policies.LoadCalculator,
        tm_factor=config.provided.progression.TM_FACTOR,
        # dict() copy: dependency-injector can't deep-copy the MappingProxyType constant.
        session_target_reps=dict(policies.DEFAULT_SESSION_TARGET_REPS),
    )
    autoregulation = providers.Singleton(
        policies.AutoregulationPolicy,
        cfg=config.provided.readiness,
        min_sessions=config.provided.autoregulation.MIN_SESSIONS_FOR_AUTOREG,
    )
    set_prescriptor = providers.Singleton(
        policies.SetPrescriptor,
        load=load_calculator,
        rest=rest_advisor,
        autoreg=autoregulation,
        tm_factor=config.provided.progression.TM_FACTOR,
    )
    fatigue_model = providers.Singleton(
        policies.FitnessFatigueModel,
        ff=config.provided.fitness_fatigue,
        load=config.provided.training_load,
        ewma=config.provided.ewma_max,
    )
    progression = providers.Singleton(
        policies.ProgressionPolicy,
        cfg=config.provided.progression,
        load=load_calculator,
    )
    plateau = providers.Singleton(policies.PlateauDetector, cfg=config.provided.plateau)
    deload = providers.Singleton(
        policies.DeloadPolicy,
        cfg=config.provided.plateau,
        plateau=plateau,
        fatigue=fatigue_model,
    )
    training_state = providers.Singleton(
        services.TrainingStateCalculator,
        fatigue=fatigue_model,
        plateau=plateau,
        deload=deload,
        trend_window_days=config.provided.plateau.TREND_WINDOW_DAYS,
    )
    schedule_builder = providers.Singleton(policies.ScheduleBuilder, cfg=config.provided.schedule)
    test_inserter = providers.Singleton(
        policies.TestSessionInserter,
        test_spacing=config.provided.schedule.DAY_SPACING["TEST"],
    )
    plan_calendar = providers.Singleton(
        services.PlanCalendar,
        schedule=schedule_builder,
        test_inserter=test_inserter,
    )
    run_factory = providers.Singleton(
        services.RunFactory,
        training_state=training_state,
        progression=progression,
        calendar=plan_calendar,
        horizon=config.provided.plan_horizon,
    )
    prescriber = providers.Singleton(
        services.Prescriber,
        load=load_calculator,
        set_prescriptor=set_prescriptor,
    )
    planning_service = providers.Factory(
        services.PlanningService,
        run_factory=run_factory,
        prescriber=prescriber,
        progression=progression,
    )
    overtraining = providers.Singleton(services.OvertrainingDetector)


container = Container()
