# FEEDIT STEP04 Metrics — Final v1.1

## Core contract

- Metric version: `feedit-step04-v1`
- Historical backfill default start: `2019-04-11`
- Legacy metric versions are not deleted by STEP04.
- Raw source facts are rebuilt from reaction / commerce / content sources; legacy metric scores are never copied into STEP04.
- `0` means observed zero. `None` means unavailable / unobserved.
- Coverage is metadata and never multiplies the score down.
- Association is explanatory and is not an input to Level.

## Scoring flow

`raw facts -> 28-day rolling source normalization -> source semantic axes -> ALL aggregation -> monthly search bridge -> temporal -> coverage`

### Rolling normalization

Count signals are normalized against the previous 28 calendar days including the target date, within the same source and signal. The cohort unit is `term-day`. Positive values receive a tie-aware percentile; observed zero stays 0 only when the rolling cohort has at least one positive observation. An all-zero/absent rolling cohort is unavailable (`None`).

This is intentionally different from a same-day percentile because historical reaction data can be sparse.

### Search

Search remains monthly and is normalized inside each platform/month cohort. It is never added to daily raw counts. The available Google/Naver platform percentiles are averaged per term and attached only to the ALL row, then blended into Attention and Intent using the configured search signal weights.

### Level / Momentum / Temperature

- Level: current semantic strength across Presence / Attention / Engagement / Intent.
- Momentum: 7-calendar-day vs 28-calendar-day movement, axis first.
- Trend Temperature: 60% Level + 40% Momentum.
- Missing dates are not silently converted to zero.

## Historical coverage found by audit

- Reaction source: 2017-11-29 ~ 2026-10-02
- Commerce snapshots: 2026-09-02 ~ 2026-10-02
- Content snapshots: 2026-09-07 ~ 2026-10-01
- Default production history begins at 2019-04-11 because this is where the existing long-form text metric history begins and the earlier reaction history is extremely sparse.

## Validation

The validator includes both STEP04 invariants and the previous upstream reaction contracts:

- score/rate ranges 0..100
- no negative core counts
- every source term has an ALL row
- unavailable normalized signals cannot carry a score
- intent code contract
- sentiment score contract
- COMMENT evidence status contract
- source-date contract for COMMENT / REVIEW

## First test

```python
from datetime import date
from pipeline.step04_metrics.runner import run_daily_metrics

result = run_daily_metrics(
    date(2026, 9, 30),
    associations=False,
    validate=True,
)
print(result)
```

Do this before historical backfill.

## Historical backfill

```python
from datetime import date
from pipeline.step04_metrics.backfill import run_backfill

result = run_backfill(
    start_date=date(2019, 4, 11),
    end_date=date(2026, 10, 1),
    associations=False,
    validate=True,
)
print(result)
```

For a large production backfill, keep associations disabled during the metric pass and rebuild associations separately afterward.

## Legacy cleanup

Do not delete `feedit-l2-v2`, `feedit-unified-text-v1`, `feedit-unified-text-v2`, or `feedit-yt-history-v1` until STEP04 historical backfill and downstream API/dashboard validation are complete.
