"""일정 계산 (plans.schedule) — 구간 나누기 공식과 "n일 남음 / n시간 남음"."""
from datetime import datetime, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from plans import schedule


def kst(*args):
    return timezone.make_aware(datetime(*args))


class SpreadTests(SimpleTestCase):
    def test_day_unit_matches_frontend_example(self):
        # 11/19 시작 · 12/03 마감 · 4개 → S = 14, L = 5, step = 3
        start, deadline = kst(2026, 11, 19), kst(2026, 12, 3, 18)
        ranges = schedule.spread(4, deadline, schedule.DAY, start)
        days = [(a.strftime('%m/%d'), b.strftime('%m/%d')) for a, b in ranges]
        self.assertEqual(days, [('11/19', '11/24'), ('11/22', '11/27'), ('11/25', '11/30'), ('11/28', '12/03')])

    def test_last_range_ends_at_deadline(self):
        deadline = kst(2026, 12, 3, 18)
        _, end = schedule.spread(3, deadline, schedule.DAY, kst(2026, 11, 19))[-1]
        self.assertEqual(end, deadline)

    def test_hour_unit_splits_hours(self):
        start, deadline = kst(2026, 11, 26, 9), kst(2026, 11, 26, 19)  # S = 10시간, L = 4, step = 3
        ranges = schedule.spread(3, deadline, schedule.HOUR, start)
        self.assertEqual([(a.hour, b.hour) for a, b in ranges], [(9, 13), (12, 16), (15, 19)])

    def test_single_checkpoint_covers_whole_span(self):
        start, deadline = kst(2026, 11, 26), kst(2026, 11, 30, 18)
        self.assertEqual(schedule.spread(1, deadline, schedule.DAY, start), [(start, deadline)])


class RemainingTests(SimpleTestCase):
    now = kst(2026, 11, 26, 10, 30)

    def test_days_left(self):
        self.assertEqual(schedule.remaining(kst(2026, 11, 29, 18), schedule.DAY, self.now)['text'], '3일 남음')

    def test_due_today(self):
        self.assertEqual(schedule.remaining(kst(2026, 11, 26, 18), schedule.DAY, self.now)['text'], '오늘 마감')

    def test_days_overdue(self):
        r = schedule.remaining(kst(2026, 11, 24, 18), schedule.DAY, self.now)
        self.assertEqual((r['text'], r['overdue']), ('2일 지남', True))

    def test_hours_left_rounds_up(self):
        # 10:30 → 15:00 = 4.5시간 → ⌈4.5⌉ = 5
        self.assertEqual(schedule.remaining(kst(2026, 11, 26, 15), schedule.HOUR, self.now)['text'], '5시간 남음')

    def test_hours_overdue(self):
        r = schedule.remaining(self.now - timedelta(hours=2), schedule.HOUR, self.now)
        self.assertEqual((r['text'], r['overdue'], r['value']), ('2시간 지남', True, -2))
