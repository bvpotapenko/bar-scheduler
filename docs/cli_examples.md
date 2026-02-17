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

```bash
$ bar-scheduler plan --start-date 2026-02-18

Current status
- Training max (TM): 9
- Latest test max: 10
- Trend (reps/week): +0.50
- Plateau: no
- Deload recommended: no
- Readiness z-score: +0.15

Upcoming Plan (4 weeks)
Date        Type  Grip      Sets (reps@kg x sets)    Rest(s)
----------  ----  --------  -----------------------  -------
2026-02-18  S     pronated  4x(4@+0.0)               240
2026-02-21  H     pronated  5x(7@+0.0)               150
2026-02-24  E     pronated  (6,5,5,4,4,4)@+0.0       60
2026-02-27  S     pronated  4x(4@+0.0)               240
...
```

## Записать тренировку

```bash
$ bar-scheduler log-session \
    --date 2026-02-18 \
    --bodyweight-kg 82 \
    --grip pronated \
    --session-type S \
    --sets "5@0/180,5@0/180,4@0/180,4@0/180"

Logged S session for 2026-02-18
Total reps: 18
Max (bodyweight): 5
```

### Формат sets

Параметр `--sets` использует формат:
```
reps@+weight/rest,reps@+weight/rest,...
```

Примеры:
- `8@0/180` - 8 reps, bodyweight only, 180s rest
- `5@+10/240` - 5 reps, +10kg added, 240s rest
- `8@0/180,6@0/120,6@0/120` - три sets с разными reps/rest

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

2. **plan** - сгенерировать первый план:
   ```bash
   bar-scheduler plan
   ```

3. **log-session** - записывать тренировки по мере выполнения:
   ```bash
   bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \
       --grip pronated --session-type S --sets "5@0/240,5@0/240,4@0/240"
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
   bar-scheduler plan
   ```
