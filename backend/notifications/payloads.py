"""알림 API 가 돌려주는 모양 = 프론트 Notification (main2/src/data/notificationStore.ts) 그대로."""
from django.utils import timezone

from handoffs.models import CardEvent
from handoffs.payloads import stamp

# 프론트 NOTIFICATION_LABEL 과 같은 글자
LABELS = {
    'request': '요청 받음', 'accept': '수락', 'propose': '날짜 제안', 'question': '질문', 'comment': '코멘트',
    'deliver': '확인 필요', 'redeliver': '확인 필요', 'fix': '수정 요청', 'confirm': '확인 완료',
    'block': '막힘', 'unblock': '막힘 해제',
}
DELIVERIES = ('deliver', 'redeliver')


def last_delivery_ids(notifications):
    """카드마다 마지막 전달 기록 id — 지금 확인을 기다리는 전달이면 알림을 누를 때 바로 확인 화면으로 가요."""
    cards = {n.card_id for n in notifications}
    last = {}
    for card_id, event_id in CardEvent.objects.filter(card_id__in=cards, kind__in=DELIVERIES).order_by('created_at', 'id').values_list('card_id', 'id'):
        last[card_id] = event_id
    return last


def notification_payload(n, last_delivery, today):
    event, card = n.event, n.card
    role = event.author_role.role_key if event.author_role else card.to_role.role_key
    review = card.status == 'delivered' and last_delivery.get(card.pk) == event.pk and not card.review_path
    return {
        'id': event.pk,
        'cardId': card.pk,
        'kind': event.kind,
        'label': LABELS[event.kind],
        'fromRole': role,
        'toRole': card.to_role.role_key if role == card.from_role.role_key else card.from_role.role_key,
        'actor': event.author_user.name,
        'title': card.title,
        'text': event.text,
        'at': stamp(event.created_at),
        'ts': int(event.created_at.timestamp() * 1000),
        'today': timezone.localtime(event.created_at).date() == today,
        'to': f'/requests/{card.pk}{"/review" if review else ""}',
        'read': n.is_read,
    }


def inbox_payload(notifications):
    notifications = list(notifications)
    last = last_delivery_ids(notifications)
    today = timezone.localdate()
    return [notification_payload(n, last, today) for n in notifications]
