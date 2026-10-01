"""The 10-working-day dispute deadline (Bangladesh MFS Regulations 2022, §17.3; rule R2).

Bangladesh's weekly holidays are Friday and Saturday, so working days are Sunday to Thursday,
minus public holidays from `config/holidays_bd.yaml`. Day zero is the day the complaint arrives;
the deadline is the end of the 10th working day after it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

from ferot import config

_WEEKDAY = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


@lru_cache
def _calendar() -> tuple[frozenset[int], frozenset[str], frozenset[date]]:
    cfg = config.holidays()
    weekend = frozenset(_WEEKDAY[d] for d in cfg.get("weekend_days", ["Friday", "Saturday"]))
    fixed = frozenset(cfg.get("fixed_dates", []))
    extra = frozenset(date.fromisoformat(d) for d in cfg.get("extra_dates", []))
    return weekend, fixed, extra


def is_working_day(d: date, extra_holidays: frozenset[date] | None = None) -> bool:
    weekend, fixed, extra = _calendar()
    if d.weekday() in weekend:
        return False
    if d.strftime("%m-%d") in fixed or d in extra:
        return False
    return not (extra_holidays and d in extra_holidays)


def add_working_days(start: date, n: int, extra_holidays: frozenset[date] | None = None) -> date:
    """Return the date of the n-th working day after `start` (start itself is day zero)."""
    d, counted = start, 0
    while counted < n:
        d += timedelta(days=1)
        if is_working_day(d, extra_holidays):
            counted += 1
    return d


def working_days_between(a: date, b: date, extra_holidays: frozenset[date] | None = None) -> int:
    """Working days in the interval (a, b]. Zero when b <= a."""
    count, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if is_working_day(d, extra_holidays):
            count += 1
    return count


def sla_status(created_at: datetime, now: datetime, limit: int | None = None) -> dict:
    limit = limit or int(config.assumptions().get("sla_working_days", 10))
    deadline = add_working_days(created_at.date(), limit)
    used = working_days_between(created_at.date(), now.date())
    left = max(limit - used, 0)
    return {
        "deadline": deadline.isoformat(),
        "working_days_limit": limit,
        "working_days_used": used,
        "working_days_left": left,
        "breached": now.date() > deadline,
    }
