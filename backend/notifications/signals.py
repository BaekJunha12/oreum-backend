from django.dispatch import receiver

from handoffs.services import events_added

from .services import notify


@receiver(events_added)
def notify_on_new_events(sender, card, events, **kwargs):
    """카드에 기록이 더해지면(만들기 · 수락 · 전달 · 확인 · 코멘트 …) 맞은편 역할에게 알림을 만들어요."""
    if events:
        notify(card, events)
