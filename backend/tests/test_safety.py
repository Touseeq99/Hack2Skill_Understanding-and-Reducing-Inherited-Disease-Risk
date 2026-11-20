import datetime

from backend.safety import is_out_of_hours, next_counsellor_window, UAE_TZ


def _t(y, m, d, h):
    return datetime.datetime(y, m, d, h, 0, tzinfo=UAE_TZ)


def test_out_of_hours_logic():
    assert not is_out_of_hours(_t(2026, 11, 18, 10))   # Wednesday 10:00
    assert is_out_of_hours(_t(2026, 11, 18, 20))       # Wednesday evening
    assert is_out_of_hours(_t(2026, 11, 21, 10))       # Saturday
    assert is_out_of_hours(_t(2026, 11, 22, 10))       # Sunday


def test_next_window_skips_weekend():
    nxt = datetime.datetime.fromisoformat(next_counsellor_window(_t(2026, 11, 20, 18)))  # Friday evening
    assert nxt.weekday() == 0 and nxt.hour == 8
