"""알림 규칙.

    notify(card, events)     새 기록마다 받는 사람을 정해 알림을 만들어요 (handoffs 의 events_added 신호로 불림)
    inbox(user)              내 알림 (새것부터, 최대 LIMIT 개)
    mark_read(user, ids)     읽음 표시 (내 것만, 없는 id 는 조용히 넘어가요)

받는 사람 = 기록을 남긴 역할의 "맞은편" 역할을 맡은 원정대원 (프론트 deriveNotifications 의 toRole 과 같은 규칙).
보내는 쪽(fromRole)이 남긴 기록이면 받는 쪽(toRole)에게, 받는 쪽이 남긴 기록이면 보내는 쪽에게 가요. 기록한 본인은 빼요.
"""
from django.db import transaction
from django.utils import timezone

from projects.models import ProjectMember

from .models import Notification

LIMIT = 200


def recipients(card, event):
    if event.author_role_id == card.from_role_id:
        roles = [card.to_role_id]
    elif event.author_role_id == card.to_role_id:
        roles = [card.from_role_id]
    else:  # 다른 역할(기획 · QA)이나 역할 없이 남긴 기록은 양쪽 모두에게
        roles = [card.from_role_id, card.to_role_id]
    users = ProjectMember.objects.filter(project=card.project_id, role_links__role__in=roles).values_list('user_id', flat=True)
    return set(users) - {event.author_user_id}


def notify(card, events):
    rows = [
        Notification(user_id=user_id, card=card, event=event, created_at=event.created_at)
        for event in events
        for user_id in sorted(recipients(card, event))
    ]
    Notification.objects.bulk_create(rows, ignore_conflicts=True)  # 같은 기록 · 같은 사람은 한 줄만 (UQ_notification_event)


def inbox(user):
    return (
        Notification.objects.filter(user=user)
        .select_related('event__author_user', 'event__author_role', 'card__from_role', 'card__to_role')
        [:LIMIT]
    )


@transaction.atomic
def mark_read(user, ids):
    """ids = 프론트 Notification.id ('카드id:기록id' = 기록 id)."""
    return Notification.objects.filter(user=user, event_id__in=ids, is_read=False).update(is_read=True, read_at=timezone.now())
