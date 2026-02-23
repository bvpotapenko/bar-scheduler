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

## Config Constants

Все константы определены в `core/config.py`:

| Constant | Default | Описание |
|----------|---------|----------|
| REST_REF_SECONDS | 180 | Reference rest interval |
| GAMMA_REST | 0.20 | Rest factor exponent |
| TAU_FATIGUE | 7 | Fatigue time constant (days) |
| TAU_FITNESS | 42 | Fitness time constant (days) |
| TM_FACTOR | 0.90 | Training max как доля от test max |
| PLATEAU_WINDOW_DAYS | 21 | Дней без PR для plateau |
| DELOAD_VOLUME_REDUCTION | 0.40 | Снижение volume при deload |
| MIN_SESSIONS_FOR_AUTOREG | 10 | Минимум сессий для autoregulation |
| WEIGHT_TM_THRESHOLD | 9 | Порог TM для добавления веса |
| WEIGHT_INCREMENT_FRACTION_PER_TM | 0.01 | 1% веса тела за каждый TM-пункт выше порога |
| MAX_ADDED_WEIGHT_KG | 20.0 | Максимальный добавленный вес |

## Источники

- Fitness-fatigue model: Banister impulse-response framework
- Rest interval effects: контролируемые исследования, сравнивающие 1-min и 3-min rest, показывают преимущества силы при более длительном rest
- Принципы progressive overload, адаптированные для bodyweight training

Полные ссылки смотрите в репозитории проекта.
