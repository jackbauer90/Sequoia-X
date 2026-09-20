from datetime import datetime
import pytest
from daily_update import target_day, update_phase, validate_coverage


def test_update_starts_at_1505_and_keeps_closed_day_before_cutoff():
    days = ['2026-09-07', '2026-09-08', '2026-09-09']
    assert target_day(days, datetime(2026, 9, 9, 15, 1)) == '2026-09-08'
    assert target_day(days, datetime(2026, 9, 9, 15, 4, 59)) == '2026-09-08'
    assert target_day(days, datetime(2026, 9, 9, 15, 5)) == '2026-09-09'
    assert target_day(days, datetime(2026, 9, 9, 18, 30)) == '2026-09-09'
    assert target_day(days, datetime(2026, 9, 12, 18, 30)) == '2026-09-09'


def test_stale_or_partial_fetch_cannot_publish():
    with pytest.raises(RuntimeError):
        validate_coverage('2026-09-08', '2026-09-09', 5000, 5000)
    with pytest.raises(RuntimeError):
        validate_coverage('2026-09-09', '2026-09-09', 4000, 5000)
    validate_coverage('2026-09-09', '2026-09-09', 4999, 5000)


def test_1505_uses_realtime_first_version_and_1830_uses_tushare_completion():
    assert update_phase(datetime(2026, 9, 11, 15, 5)) == 'realtime'
    assert update_phase(datetime(2026, 9, 11, 18, 29, 59)) == 'realtime'
    assert update_phase(datetime(2026, 9, 11, 18, 30)) == 'tushare'
