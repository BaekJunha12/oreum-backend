"""알림 모양 — 프론트 main2/src/data/notificationStore.ts 의 Notification 그대로."""
from django.utils import timezone

from handoffs import dates
from handoffs.payloads import role_ref

from .services import LABEL, front_id


def notification_payload(n, today_start=None):
    card, event = n.card, n.event
    today_start = today_start or timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    review = card.status == 'delivered' and event.kind in ('deliver', 'redeliver') and not card.review_path
    return {
        'id': front_id(n),
        'serverId': str(n.pk),
        'cardId': card.id,
        'kind': event.kind,
        'label': LABEL.get(event.kind, event.kind),
        'fromRole': role_ref(card.from_role),
        'toRole': role_ref(card.to_role),
        'actor': event.author_user.name,
        'title': card.title,
        'text': event.text,
        'at': dates.stamp(event.created_at),
        'ts': dates.millis(event.created_at),
        'today': event.created_at >= today_start,
        'to': f'/requests/{card.id}/review' if review else (card.review_path or f'/requests/{card.id}'),
        'read': n.is_read,
        'blocked': card.blocked_since is not None and card.status != 'confirmed',
    }
