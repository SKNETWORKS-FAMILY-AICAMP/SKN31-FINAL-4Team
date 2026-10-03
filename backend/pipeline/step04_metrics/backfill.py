from __future__ import annotations

from datetime import date, timedelta
from .config import HISTORICAL_START_DATE, METRIC_VERSION
from .runner import run_daily_metrics


def run_backfill(start_date: date | None = None, end_date: date | None = None,
                 *, metric_version: str = METRIC_VERSION, associations: bool = False,
                 validate: bool = True):
    start_date = start_date or date.fromisoformat(HISTORICAL_START_DATE)
    end_date = end_date or date.today()
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    current = start_date
    done = 0
    failed = 0
    while current <= end_date:
        print(f"[{current}] START")
        try:
            result = run_daily_metrics(current, metric_version=metric_version,
                                       associations=associations, validate=validate)
            ok = (result.get("validation") or {}).get("ok") if validate else True
            print(f"[{current}] DONE rows={(result.get('validation') or {}).get('rows')} validation={ok}")
            done += 1
        except Exception as exc:
            failed += 1
            print(f"[{current}] FAILED {type(exc).__name__}: {exc}")
            raise
        current += timedelta(days=1)
    return {"start_date": str(start_date), "end_date": str(end_date), "done": done, "failed": failed}
