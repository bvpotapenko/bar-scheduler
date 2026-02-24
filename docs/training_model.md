# Документация модели тренировок

Этот документ объясняет формулы и логику адаптации, используемые bar-scheduler для генерации планов тренировок подтягиваний.

## Обзор

Система использует **fitness-fatigue impulse response model** (семейство моделей Banister) в сочетании с метриками, скорректированными на отдых, чтобы:

1. Оценить текущую производительность подтягиваний из истории тренировок
2. Количественно оценить тренировочную нагрузку на основе объема, интенсивности и отдыха
3. Моделировать fatigue/readiness во времени
4. Генерировать персонализированные многонедельные планы для достижения цели в 30 строгих подтягиваний

## Ключевые концепции

### Стандартизированный тест

Все сравнения "max reps" стандартизированы:
- **Movement**: Строгое подтягивание (из виса до подбородка над перекладиной)
- **Grip**: pronated (ладони от себя)
- **External load**: 0 kg (только вес тела)
- **Reference rest**: 180 секунд

### Training Max (TM)

Training max рассчитывается как 90% от последнего test max:

```
TM = floor(0.9 * latest_test_max)
```

Это обеспечивает консервативную базу для назначений. Все сессии плана стартуют с этого значения и прогрессируют вверх — никогда с raw test_max напрямую.

## Added Weight (Strength Sessions)

Для S-сессий добавленный вес масштабируется относительно веса тела:

```
added_weight = round(bodyweight_kg × 0.01 × (TM - 9), nearest 0.5 kg)
               clamped to [0, 20 kg]
```

Это даёт одинаковый относительный стимул для атлетов разного веса. Вес добавляется только когда TM > 9.

## Adaptive Rest

Рекомендованное время отдыха адаптируется на основе последней сессии того же типа:

- Базовое значение: середина диапазона `(rest_min + rest_max) / 2`
- RIR ≤ 1 хотя бы в одном подходе → +30s
- Drop-off > 35%: первый vs последний подход → +15s
- Readiness z < –1.0 → +30s
- Все подходы RIR ≥ 3 → –15s
- Итог ограничен диапазоном `[rest_min, rest_max]`

## Rest Normalization

Отдых между подходами влияет как на производительность, так и на накопление fatigue. Исследования показывают, что более длительный отдых (3+ минуты) поддерживает лучшие силовые результаты по сравнению с коротким отдыхом (1 минута).

### Формула rest_factor

```
F_rest(r) = clip((r/180)^0.20, 0.80, 1.05)
```

Где:
- `r` = rest_seconds между подходами
- 180s = REST_REF_SECONDS
- Экспонента GAMMA_REST = 0.20 обеспечивает плавное масштабирование
- Ограничено между F_REST_MIN и F_REST_MAX

**Интерпретация**: Короткий rest (< 180s) дает F_rest < 1, что означает, что эти reps "сложнее" и получают больше кредита при нормализации.

## Fitness-Fatigue Model

Система поддерживает две переменные состояния, обновляемые ежедневно:

### Fitness (G) - медленное затухание
```
G(t) = G(t-1) * e^(-1/TAU_FITNESS) + K_FITNESS * w(t)
```

### Fatigue (H) - быстрое затухание
```
H(t) = H(t-1) * e^(-1/TAU_FATIGUE) + K_FATIGUE * w(t)
```

### Readiness
```
R(t) = G(t) - H(t)
```

Где:
- `TAU_FITNESS = 42` дня (постоянная времени fitness)
- `TAU_FATIGUE = 7` дней (постоянная времени fatigue)
- `w(t)` = training load impulse для дня t

## Расчет Training Load

Дневная training load вычисляется из подходов:

```
w(t) = sum(HR_j * S_load_j * S_grip_j)
```

Где:
- `HR_j` = Hard Reps = reps * effort_multiplier(RIR)
- `S_load_j` = load stress multiplier (added_weight)
- `S_grip_j` = grip stress factor

Примечание: rest_stress_multiplier намеренно **исключён** из training load. Короткий отдых уже учтён через `effective_reps()` (нормализация производительности), поэтому его включение в w(t) приводило бы к двойному подсчёту.

### Effort Multiplier
```
E_rir(rir) = 1 + A_RIR * max(0, 3 - rir)
```

Подходы ближе к failure (ниже RIR) вносят больший вклад в training load.

## Session Types

| Type | Описание | Reps fraction of TM | Rest | Sets |
|------|----------|---------------------|------|------|
| S | Strength (сила) | 0.35–0.55 × TM (4–6 abs) | 180–300s | 4–5 |
| H | Hypertrophy (гипертрофия) | 0.60–0.85 × TM (6–12 abs) | 120–180s | 4–6 |
| E | Endurance/Density (выносливость) | 0.40–0.60 × TM (3–8 abs) | 45–75s | 6–10 |
| T | Technique (техника) | 0.20–0.40 × TM (2–4 abs) | 60–120s | 4–8 |
| TEST | Max test | — | 180–300s | 1 |

### Weekly Schedules

Fixed day-offset patterns to maintain true 7-day weeks:
- **3 days/week**: Mon(+0), Wed(+2), Fri(+4) → S, H, E
- **4 days/week**: Mon(+0), Tue(+1), Thu(+3), Sat(+5) → S, H, T, E

### Autoregulation

Autoregulation (adjusting sets/reps based on readiness z-score) activates only after **10+ logged sessions** (`MIN_SESSIONS_FOR_AUTOREG = 10`) to ensure the fitness-fatigue model has enough data to calibrate reliably.

## Adaptation Rules

### Plateau Detection
Plateau обнаруживается когда:
1. Trend slope < PLATEAU_SLOPE_THRESHOLD (0.05 reps/week)
2. Нет нового personal best за PLATEAU_WINDOW_DAYS (21 день)

### Deload Triggers
Deload рекомендуется при любом из:
1. Plateau И readiness z-score < FATIGUE_Z_THRESHOLD (-0.5)
2. Две последовательных strength sessions с underperformance (> UNDERPERFORMANCE_THRESHOLD)
3. Weekly compliance_ratio < COMPLIANCE_THRESHOLD (0.70)

### Volume Adjustments
- **Deload**: Снижение volume на DELOAD_VOLUME_REDUCTION (40%)
- **Low readiness (z < READINESS_Z_LOW)**: Снижение volume на READINESS_VOLUME_REDUCTION (30%)
- **High readiness (z > READINESS_Z_HIGH) + good compliance**: Допускается увеличение на WEEKLY_VOLUME_INCREASE_RATE (10%)

## Progression

Progression замедляется по мере приближения training_max к TARGET_MAX_REPS:

```
delta_per_week = DELTA_PROGRESSION_MIN + (DELTA_PROGRESSION_MAX - DELTA_PROGRESSION_MIN) * (1 - TM/30)^ETA_PROGRESSION
```

Это реализует нелинейную кривую где:
- Ранний прогресс: ~0.5 reps/week
- Около 30: ~0.1 reps/week

**Применение прогрессии**: progression добавляется один раз при переходе между календарными неделями (граница = 7 дней от начала плана). Все сессии в пределах одной недели получают одинаковый TM.

## Plan Stability

Для обеспечения стабильности плана:

- **Прошедшие сессии**: предписанные подходы берутся из записанных `planned_sets` (заморожены в момент логирования), а не перегенерируются каждый раз.
- **Ротация типов сессий**: план продолжает ротацию (S→H→E или S→H→T→E) с позиции, следующей за последней записанной non-TEST сессией.
- **Нумерация недель**: недели нумеруются кумулятивно от первой сессии в истории (не от начала текущего плана).

## Endurance Volume (kE)

Общий объём E-сессии (total_target) масштабируется с TM:

```
kE(TM) = 3.0 + 2.0 × clip((TM - 5) / 25, 0, 1)
total_target = int(kE(TM) * TM)
```

kE растёт от 3.0 (TM=5) до 5.0 (TM=30), давая пропорционально больший объём по мере роста атлета.

## ExerciseDefinition Schema

Each supported exercise is described by an `ExerciseDefinition` dataclass
(`core/exercises/base.py`).  The planner engine is fully parameterised by this
object — no exercise-specific code exists outside the exercise files.

```python
@dataclass(frozen=True)
class ExerciseDefinition:
    exercise_id: str           # "pull_up" | "dip" | "bss"
    display_name: str          # Human-readable name
    muscle_group: str          # "upper_pull" | "upper_push" | "lower"

    # Load model
    bw_fraction: float         # Fraction of BW that is the load
    load_type: str             # "bw_plus_external" | "external_only"

    # Variants (equivalent to grips for pull-ups)
    variants: list[str]
    primary_variant: str
    variant_factors: dict[str, float]

    # Session parameters per session type
    grip_cycles: dict[str, list[str]]
    session_params: dict[str, SessionTypeParams]

    # Goal
    target_metric: str         # "max_reps"
    target_value: float        # e.g. 30 reps

    # Assessment
    test_protocol: str
    test_frequency_weeks: int

    # 1RM display
    onerm_includes_bodyweight: bool
    onerm_explanation: str

    # Added weight formula
    weight_increment_fraction: float  # % of BW per TM point above threshold
    weight_tm_threshold: int
    max_added_weight_kg: float
```

### bw_fraction and Effective Load (Leff)

The **effective load** formula is the backbone of all load-based calculations:

```
Leff = BW × bw_fraction + added_weight_kg − assistance_kg
```

| Exercise | bw_fraction | Justification |
|----------|------------|---------------|
| Pull-Up  | 1.00 | Near-100 % of BW is displaced vertically |
| Dip      | 0.92 | Hands/forearms (~5 % BW) fixed; upper arms rotate (~3 % reduction). McKenzie et al. 2022 |
| BSS (DB) | 0.71 | Lead leg bears ~71 % of total BW. Mackey & Riemann 2021 |

`bw_fraction` matters for:
- Rest normalization (standardised reps scaled by `(Leff / Leff_ref)^γ`)
- Training load (load_stress_multiplier)
- 1RM estimation (Epley applied to Leff)

For BSS, `load_type = "external_only"` means the planner uses the last TEST
dumbbell weight for prescription, while `bw_fraction = 0.71` still applies to
all Leff and load-stress calculations.

---

## 1RM Estimation

The planner uses the **Epley formula** to estimate 1-rep max from multi-rep sets:

```
1RM = total_load × (1 + reps / 30)
```

Where `total_load` depends on the exercise:

```
total_load = BW × bw_fraction + added_weight_kg   (pull-up, dip, BSS)
```

### Accuracy

The Epley formula is validated for **1–10 rep ranges**.  Estimates from 10+ reps
are less reliable and should be treated as lower bounds.

### Bodyweight inclusion

| Exercise | BW included? | Why |
|----------|-------------|-----|
| Pull-Up  | Yes (×1.0)  | You lift your entire bodyweight |
| Dip      | Yes (×0.92) | You lift ~92 % of your bodyweight |
| BSS (DB) | Yes (×0.71) | Lead leg bears ~71 % of BW — included for comparability |

The 1RM command shows an explanation string from `ExerciseDefinition.onerm_explanation`
for each exercise.

```bash
bar-scheduler 1rm --exercise pull_up
bar-scheduler 1rm --exercise dip
bar-scheduler 1rm --exercise bss
```

---

## Plan Regeneration (Immutable History)

Past prescriptions are **frozen** — they are stored in `planned_sets` at the
time of logging and never re-generated from the current model state.

When you run `bar-scheduler plan`:

1. **Past sessions** use `planned_sets` from the history file as-is.
2. **Future sessions** are freshly generated from the current `UserState`.
3. The plan **resumes** the session-type rotation from the last logged non-TEST
   session (not from the beginning of the cycle).
4. Week numbers increment **cumulatively** from the first session in history.

This means: if you change bodyweight, get a new TEST result, or update
equipment, **only future sessions change**.  Your training log is never
retroactively modified.

### plan_start_date

The field `plan_start_date` in `profile.json` anchors the timeline.  Use
`bar-scheduler skip` to advance it (rest days, travel) without losing history.

---

## Config Constants (YAML and Python)

Constants are defined in two places:

- **`src/bar_scheduler/exercises.yaml`** — documented YAML file, used as the
  primary reference.  You can create a user override at
  `~/.bar-scheduler/exercises.yaml` to customise any value without editing code.
- **`core/config.py`** — Python constants loaded at import time.  Values here
  match the bundled YAML defaults exactly.

The loader (`core/engine/config_loader.py`) merges the bundled YAML with your
user override on startup.

| Constant | YAML path | Default | Description |
|----------|-----------|---------|-------------|
| `REST_REF_SECONDS` | `rest_normalization.REST_REF_SECONDS` | 180 | Reference rest interval (s) |
| `GAMMA_REST` | `rest_normalization.GAMMA_REST` | 0.20 | Rest factor exponent |
| `TAU_FATIGUE` | `fitness_fatigue.TAU_FATIGUE` | 7 | Fatigue time constant (days) |
| `TAU_FITNESS` | `fitness_fatigue.TAU_FITNESS` | 42 | Fitness time constant (days) |
| `TM_FACTOR` | `progression.TM_FACTOR` | 0.90 | Training max / test max ratio |
| `PLATEAU_WINDOW_DAYS` | `plateau.PLATEAU_WINDOW_DAYS` | 21 | Days without PR = plateau |
| `DELOAD_VOLUME_REDUCTION` | `volume.DELOAD_VOLUME_REDUCTION` | 0.40 | Volume cut in deload (40%) |
| `MIN_SESSIONS_FOR_AUTOREG` | `autoregulation.MIN_SESSIONS_FOR_AUTOREG` | 10 | Gate for autoregulation |

## Источники

- Fitness-fatigue model: Banister impulse-response framework
- Rest interval effects: контролируемые исследования, сравнивающие 1-min и 3-min rest, показывают преимущества силы при более длительном rest
- Принципы progressive overload, адаптированные для bodyweight training

Полные ссылки смотрите в репозитории проекта.
