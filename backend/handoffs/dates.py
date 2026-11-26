"""카드의 날짜 글자 ↔ 날짜 (프론트 requestStore.ts 의 parseWhen · stamp 와 같은 규칙).

프론트는 날짜를 화면 글자 그대로 주고받아요: '11/21 (금) 18:00' · '오늘 18:00' · '내일' · '체크포인트 2'.
서버는 글자를 그대로 저장하고(due_label), 날짜로 읽히면 due_at 도 채워요 (정렬 · 마감 지남 계산용).
"""
import re
from datetime import datetime, timedelta

from django.utils import timezone

MD = re.compile(r'(\d{1,2})\s*/\s*(\d{1,2})')
HM = re.compile(r'(\d{1,2}):(\d{2})')


def parse_when(text, now=None):
    """'11/21 (금) 18:00' → 한국 시간 datetime. 날짜가 없는 글자('체크포인트 2')는 None.

    해는 지금 해로 보고, 그 날짜가 6달 넘게 지났으면 내년으로 봐요 (12월에 '1/05' 라고 쓰면 다음 해).
    """
    if not text:
        return None
    now = timezone.localtime(now or timezone.now())
    md, hm = MD.search(text), HM.search(text)
    if md:
        month, day = int(md.group(1)), int(md.group(2))
    elif '내일' in text:
        tomorrow = now + timedelta(days=1)
        month, day = tomorrow.month, tomorrow.day
    elif '오늘' in text:
        month, day = now.month, now.day
    else:
        return None
    hour, minute = (int(hm.group(1)), int(hm.group(2))) if hm else (23, 59)
    try:
        when = timezone.make_aware(datetime(now.year, month, day, min(hour, 23), min(minute, 59)))
    except ValueError:
        return None
    if (now - when).days > 183:
        when = when.replace(year=now.year + 1)
    return when


def stamp(dt):
    """'11/18 11:00' (기록의 at)."""
    d = timezone.localtime(dt)
    return f'{d.month:02d}/{d.day:02d} {d.hour:02d}:{d.minute:02d}'


def day_stamp(date):
    """'11/18' (막힌 날)."""
    return f'{date.month:02d}/{date.day:02d}'


def due_short(label):
    """'11/21 (금) 18:00' → '11/21 18:00'."""
    return re.sub(r'\s*\([^)]*\)', '', label or '').strip()


def due_day(label):
    """'11/21 (금) 18:00' → '11/21'."""
    return re.sub(r'\s*\d{1,2}:\d{2}$', '', due_short(label)).strip() or label


def millis(dt):
    return int(dt.timestamp() * 1000)


def from_millis(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.get_current_timezone())
