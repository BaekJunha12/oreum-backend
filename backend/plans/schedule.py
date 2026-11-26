"""일정 계산 — 구간 기간 나누기 · 남은 시간 ("n일 남음" / "n시간 남음").

구간 기간 (프론트 planStore.checkpointRanges 와 같은 규칙, 단위만 일 · 시간 둘 다):

    S    = 시작 ~ 마감 길이 (단위 = 일 또는 시간)
    L    = max(1, round(0.36 · S))          구간 하나의 길이 (전체의 약 36%)
    step = (S − L) / (n − 1)                구간끼리 시작 간격 (n = 구간 수, n = 1 이면 0)
    i 번째 구간 = [시작 + round(i·step),  시작 + round(i·step + L)]   (마지막 구간은 마감에 끝남)

    예) 11/19 시작 · 12/03 마감 · 4개 → S = 14, L = 5, step = 3
        11/19–11/24, 11/22–11/27, 11/25–11/30, 11/28–12/03   (구간끼리 겹쳐서 디자인 → 프론트 → 백이 이어 받음)
"""
import math
from datetime import datetime, time, timedelta

from django.utils import timezone

DAY, HOUR = 'day', 'hour'
OVERLAP = 0.36


def _local(dt):
    return timezone.localtime(dt)


def start_point(unit, now=None):
    """일정을 나누기 시작하는 때: 일 단위 = 오늘 0시, 시간 단위 = 지금 시각을 정시로 올림."""
    now = _local(now or timezone.now())
    if unit == HOUR:
        floor = now.replace(minute=0, second=0, microsecond=0)
        return floor if floor == now else floor + timedelta(hours=1)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def spread(n, deadline, unit, start=None):
    """구간 n 개의 [(시작, 목표)] — 위 수식. 마감이 시작보다 앞이면 모두 마감 시각 한 점으로."""
    if n <= 0:
        return []
    deadline = _local(deadline)
    start = _local(start) if start else start_point(unit)
    step_unit = timedelta(hours=1) if unit == HOUR else timedelta(days=1)

    if unit == HOUR:
        span = math.ceil((deadline - start) / step_unit)
    else:
        span = (deadline.date() - start.date()).days
    if span <= 0:
        return [(deadline, deadline)] * n

    length = max(1, round(span * OVERLAP))
    step = (span - length) / (n - 1) if n > 1 else 0

    def at(k, end=False):
        point = start + step_unit * round(k)
        if unit == DAY and end:
            # 일 단위 목표는 그날의 마감 시각(예: 18:00)으로
            point = point.replace(hour=deadline.hour, minute=deadline.minute)
        return min(point, deadline)

    out = []
    for i in range(n):
        begin = at(i * step)
        finish = deadline if i == n - 1 else at(i * step + length, end=True)
        out.append((begin, max(begin, finish)))
    return out


def remaining(deadline, unit, now=None):
    """마감까지 남은 양. { unit, value, overdue, text }

    일 단위   value = 마감 날짜 − 오늘 날짜 (달력 기준)   → 'n일 남음' · '오늘 마감' · 'n일 지남'
    시간 단위 value = ⌈(마감 − 지금) / 1시간⌉            → 'n시간 남음' · 'n시간 지남'
    """
    if deadline is None:
        return None
    now = _local(now or timezone.now())
    deadline = _local(deadline)
    if unit == HOUR:
        seconds = (deadline - now).total_seconds()
        hours = math.ceil(abs(seconds) / 3600) if seconds else 0
        if seconds >= 0:
            return {'unit': HOUR, 'value': hours, 'overdue': False, 'text': f'{hours}시간 남음' if hours else '마감 시각'}
        return {'unit': HOUR, 'value': -hours, 'overdue': True, 'text': f'{hours}시간 지남'}
    days = (deadline.date() - now.date()).days
    if days > 0:
        text = f'{days}일 남음'
    elif days == 0:
        text = '오늘 마감'
    else:
        text = f'{-days}일 지남'
    return {'unit': DAY, 'value': days, 'overdue': deadline < now, 'text': text}


def combine(date_value, time_value):
    """프론트 Plan 의 date('YYYY-MM-DD') + time('HH:MM') → 한국 시간 datetime."""
    return timezone.make_aware(datetime.combine(date_value, time_value or time(18, 0)))


WEEKDAY = '월화수목금토일'


def range_label(start, end, unit):
    """화면 칩 글자: 일 단위 '11/19 – 11/24' · 시간 단위 '11/19 09:00 – 15:00'."""
    if not start or not end:
        return ''
    s, e = _local(start), _local(end)
    md = lambda d: f'{d.month}/{d.day:02d}'  # noqa: E731 — 프론트 checkpointRanges 와 같은 모양
    if unit == HOUR:
        tail = e.strftime('%H:%M') if s.date() == e.date() else f'{md(e)} {e.strftime("%H:%M")}'
        return f'{md(s)} {s.strftime("%H:%M")} – {tail}'
    return f'{md(s)} – {md(e)}'
