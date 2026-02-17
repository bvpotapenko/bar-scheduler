# Примеры CLI

Этот документ показывает примеры команд и вывода для bar-scheduler.

## Инициализация нового пользователя

```bash
$ bar-scheduler init --height-cm 180 --sex male --days-per-week 3 --bodyweight-kg 82 --baseline-max 10

Initialized profile at /Users/you/.bar-scheduler/profile.json
History file: /Users/you/.bar-scheduler/history.jsonl
Logged baseline test: 10 reps
Training max: 9
```

При наличии существующей history будет предложено:
- Сохранить существующую (обновить только profile)
- Переименовать в `history_old.jsonl` и начать заново
- Отменить

Для пропуска диалога: `--force`

## Показать историю тренировок

```bash
$ bar-scheduler show-history

Date        Type  Grip      BW(kg)  Max(BW)  Total reps  Avg rest(s)
----------  ----  --------  ------  -------  ----------  -----------
2026-02-01  TEST  pronated  82.0    10       10          180
2026-02-04  S     pronated  82.0    5        20          240
2026-02-06  H     neutral   82.0    9        42          150
```

## Сгенерировать план тренировок

Plan показывает recent history, current status, и upcoming sessions с маркером `>` показывающим следующую session:

```bash
$ bar-scheduler plan -w 4

Recent History
Date        Type  Grip      Sets  Total  Max
----------  ----  --------  ----  -----  ---
2026-02-01  TEST  pronated     1     10   10
2026-02-04  S     pronated     4     20    5
2026-02-06  H     neutral      5     30    8

Current status
- Training max (TM): 9
- Latest test max: 10
- Trend (reps/week): +0.00
- Plateau: no
- Deload recommended: no
- Readiness z-score: +0.12

Last session: 2026-02-06 (H)
Trained yesterday

                            Upcoming Plan (4 weeks)
    Wk  Date        Type  Grip      Sets (reps@kg x sets)   Rest  Total  TM
--  --  ----------  ----  --------  ----------------------  ----  -----  --
 >   1  2026-02-08  E     pronated  (4,3,3,3,3,3,3,3)@+0.0    60      28   9
     1  2026-02-11  S     pronated  4x(5@+0.0)               240      20   9
     1  2026-02-14  H     pronated  5x(6@+0.0)               120      30   9
     2  2026-02-17  E     pronated  (4,3,3,3,3,3,3,3)@+0.0    60      28   9
     ...
     4  2026-03-03  S     pronated  4x(5@+2.5)               240      20  10
```

Колонки:
- **>** - маркер следующей session
- **Wk** - номер недели
- **Total** - сумма reps за session
- **TM** - expected Training Max после выполнения этой session

Plan автоматически начинается после последней logged session (не с завтрашнего дня).

## Записать тренировку

```bash
$ bar-scheduler log-session \
    --date 2026-02-18 \
    --bodyweight-kg 82 \
    --grip pronated \
    --session-type S \
    --sets "5@0/180, 5@0/180, 4@0"

Logged S session for 2026-02-18
Total reps: 14
Max (bodyweight): 5
```

### Формат sets

Параметр `--sets` использует формат:
```
reps@+weight/rest,reps@+weight/rest,...
```

Rest можно не указывать для последнего set:

Примеры:
- `8@0/180` - 8 reps, bodyweight only, 180s rest
- `5@+10/240` - 5 reps, +10kg added, 240s rest
- `8@0/180, 6@0/120, 6@0` - три sets, rest для последнего = 0

### Overperformance detection

Если max reps в session значительно превышает Training Max, будет предложено logged TEST session:

```bash
$ bar-scheduler log-session \
    --date 2026-02-18 \
    --bodyweight-kg 82 \
    --grip pronated \
    --session-type H \
    --sets "12@0/120, 10@0/120, 9@0"

Logged H session for 2026-02-18
Total reps: 31
Max (bodyweight): 12

Warning: Great performance! Your max (12) exceeds TM (9) by 3 reps.
This also beats your latest test max (10). Consider logging a TEST session to update your baseline!
```

## График прогресса max reps

```bash
$ bar-scheduler plot-max

Max Reps Progress (Strict Pull-ups)
──────────────────────────────────────────────────────────────
 30 ┤
 28 ┤
 26 ┤
 24 ┤
 22 ┤                                      ╭──● (23)
 20 ┤                                  ╭───╯
 18 ┤                              ╭───╯
 16 ┤                      ╭──● (16)
 14 ┤                  ╭───╯
 12 ┤          ╭──● (12)
 10 ┤      ╭───╯
  8 ● (8)──╯
  6 ┤
──────────────────────────────────────────────────────────────
    Feb 01   Feb 15   Mar 01   Mar 15   Apr 01   Apr 15
```

## Обновить bodyweight

```bash
$ bar-scheduler update-weight --bodyweight-kg 80.5

Updated bodyweight to 80.5 kg
```

## Проверить training status

```bash
$ bar-scheduler status

Current status
- Training max (TM): 12
- Latest test max: 14
- Trend (reps/week): +0.45
- Plateau: no
- Deload recommended: no
- Readiness z-score: +0.23
```

## Диаграмма weekly volume

```bash
$ bar-scheduler volume --weeks 4

Weekly Volume (Total Reps)
─────────────────────────────────────────────────
3 weeks ago │████████████████████ 85.0
2 weeks ago │███████████████████████████ 115.0
Last week   │██████████████████████████████ 128.0
This week   │██████████ 42.0
```

## Использование custom history path

Все команды принимают `--history-path` для использования нестандартного расположения:

```bash
$ bar-scheduler init --history-path ./my_training/history.jsonl --bodyweight-kg 82

$ bar-scheduler plan --history-path ./my_training/history.jsonl
```

## Типичный workflow

1. **init** - инициализировать профиль с baseline test:
   ```bash
   bar-scheduler init --bodyweight-kg 82 --baseline-max 10
   ```

2. **plan** - сгенерировать план на 10+ недель:
   ```bash
   bar-scheduler plan -w 10
   ```

3. **log-session** - записывать тренировки по мере выполнения:
   ```bash
   bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
       --grip pronated --session-type S --sets "5@0/240, 5@0/240, 4@0"
   ```

4. **plot-max** и **status** - проверять прогресс периодически:
   ```bash
   bar-scheduler plot-max
   bar-scheduler status
   ```

5. **update-weight** - обновлять bodyweight когда он меняется:
   ```bash
   bar-scheduler update-weight --bodyweight-kg 81
   ```

6. **plan** - перегенерировать план еженедельно или после TEST sessions:
   ```bash
   bar-scheduler plan -w 8
   ```

## Документация модели

- Подробная математическая модель: [core_training_formulas_fatigue.md](../core_training_formulas_fatigue.md)
- Научные источники: [REFERENCES.md](../REFERENCES.md)
