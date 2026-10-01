from datetime import date, datetime

from ferot.policy.sla import add_working_days, is_working_day, sla_status, working_days_between


def test_friday_and_saturday_are_not_working_days():
    assert not is_working_day(date(2026, 10, 2))  # Friday
    assert not is_working_day(date(2026, 10, 3))  # Saturday
    assert is_working_day(date(2026, 10, 4))  # Sunday


def test_fixed_public_holiday_is_skipped():
    assert not is_working_day(date(2026, 12, 16))  # Victory Day


def test_ten_working_days_from_a_thursday():
    # Complaint on Thu 1 Oct 2026: Sun 4 .. Thu 8 (5), Sun 11 .. Thu 15 (10).
    assert add_working_days(date(2026, 10, 1), 10) == date(2026, 10, 15)


def test_extra_holiday_pushes_the_deadline():
    extra = frozenset({date(2026, 10, 6)})
    assert add_working_days(date(2026, 10, 1), 10, extra) == date(2026, 10, 18)


def test_working_days_between_counts_half_open_interval():
    assert working_days_between(date(2026, 10, 1), date(2026, 10, 1)) == 0
    assert working_days_between(date(2026, 10, 1), date(2026, 10, 4)) == 1


def test_sla_status_reports_breach():
    created = datetime(2026, 10, 1, 9, 0)
    on_time = sla_status(created, datetime(2026, 10, 8, 12, 0))
    assert on_time["working_days_left"] == 5 and not on_time["breached"]
    late = sla_status(created, datetime(2026, 10, 18, 12, 0))
    assert late["breached"]
