"""Calendar config sections (plan horizon, weekly schedule templates)."""

from dataclasses import dataclass, field


@dataclass
class PlanHorizonConfig:
    MIN_PLAN_WEEKS: int = 2
    MAX_PLAN_WEEKS: int = 52
    DEFAULT_PLAN_WEEKS: int = 4


@dataclass
class ScheduleConfig:
    SCHEDULE_1_DAYS: list[str] = field(default_factory=lambda: ["S"])
    SCHEDULE_2_DAYS: list[str] = field(default_factory=lambda: ["S", "H"])
    SCHEDULE_3_DAYS: list[str] = field(default_factory=lambda: ["S", "H", "E"])
    SCHEDULE_4_DAYS: list[str] = field(default_factory=lambda: ["S", "H", "T", "E"])
    SCHEDULE_5_DAYS: list[str] = field(default_factory=lambda: ["S", "H", "T", "E", "S"])
    DAY_SPACING: dict[str, int] = field(
        default_factory=lambda: {"S": 1, "H": 1, "E": 1, "T": 0, "TEST": 1},
    )
