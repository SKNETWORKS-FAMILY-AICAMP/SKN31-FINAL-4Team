from datetime import date
from pprint import pprint

from .runner import run_daily_metrics


def run(test_date: date = date(2026, 9, 30)):
    result = run_daily_metrics(test_date, associations=False, validate=True)
    pprint(result)
    return result
