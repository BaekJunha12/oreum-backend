"""알림 규칙.

카드에 기록이 한 줄 생기면(notify_event) 받을 사람을 골라 한 줄씩 만들어요.
    받는 사람 = 기록을 남긴 사람의 "반대쪽" 역할을 맡은 원정대원 + 카드의 담당자(maker · requester)
                (기록을 남긴 사람은 빼요 — 내가 한 일은 알림이 아니에요)
    코멘트 · 질문은 양쪽 모두에게 가요.
"""
from django.db import transaction
from django.utils import timezone

from projects.models import ProjectMember

from .models import Notification

LABEL = {
    'request': '요청 받음', 'accept': '수락', 'propose': '날짜 제안', 'question': '질문', 'comment': '코멘트',
    'deliver': '확인 필요', 'redeliver': '확인 필요', 'fix': '수정 요청', 'confirm': '확인 완료', 'block': '막힘', 'unblock': '막힘 해제',
}
# 기록 종류 → 알림을 받을 쪽 (from = 만드는 쪽, to = 요청한 쪽)
AUDIENCE = {
    'request': {'from'}, 'accept': {'to'}, 'propose': {'to'}, 'deliver': {'to'}, 'redeliver': {'to'},
    'confirm': {'from'}, 'fix': {'from'}, 'block': {'from'}, 'unblock': {'from'},
    'comment': {'from', 'to'}, 'question': {'from', 'to'},
}


def recipients(event):
    card = event.card
    sides = AUDIENCE.get(event.kind, {'from', 'to'})
    role_ids, users = set(), set()
    if 'from' in sides:
        role_ids.add(card.from_role_id)
        if card.maker_user_id:
            users.add(card.maker_user_id)
    if 'to' in sides:
        role_ids.add(card.to_role_id)
        if card.requester_user_id:
            users.add(card.requester_user_id)
    users |= set(ProjectMember.objects.filter(project_id=card.project_id, role_links__role_id__in=role_ids).values_list('user_id', flat=True))
    users.discard(event.author_user_id)
    return users


def notify_event(event):
    Notification.objects.bulk_create(
        [Notification(user_id=uid, card_id=event.card_id, event=event) for uid in recipients(event)],
        ignore_conflicts=True,
    )


def for_user(user, project=None):
    qs = Notification.objects.filter(user=user).select_related(
        'card__from_role', 'card__to_role', 'card', 'event__author_user', 'event__author_role',
    )
    if project is not None:
        qs = qs.filter(card__project=project)
    return qs


def front_id(n):
    """프론트 알림 id = '{카드 id}:{기록 id}'."""
    return f'{n.card_id}:{n.event_id}'


@transaction.atomic
def mark_read(user, ids=None):
    """ids = 프론트 알림 id('{카드}:{기록}') 또는 서버 알림 id 목록. None 이면 모두 읽음."""
    qs = Notification.objects.filter(user=user, is_read=False)
    if ids is not None:
        event_ids = [i.split(':', 1)[1] for i in ids if ':' in i]
        pks = [int(i) for i in ids if i.isdigit()]
        qs = qs.filter(event_id__in=event_ids) | qs.filter(pk__in=pks)
    return qs.update(is_read=True, read_at=timezone.now())
