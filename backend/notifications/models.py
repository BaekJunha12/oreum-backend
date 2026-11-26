"""E. 알림 (docs/db/erd.sql). 카드 기록(card_events) 한 줄 → 받는 사람마다 알림 한 줄."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from handoffs.models import CardEvent, HandoffCard


class Notification(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='notification_id')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    card = models.ForeignKey(HandoffCard, on_delete=models.CASCADE, related_name='+')
    event = models.ForeignKey(CardEvent, on_delete=models.CASCADE, related_name='notifications')
    is_read = models.BooleanField('읽음', default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'notifications'
        verbose_name = verbose_name_plural = '알림'
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['user', 'is_read', 'created_at'], name='IX_notification_inbox')]
        constraints = [models.UniqueConstraint(fields=['user', 'event'], name='UQ_notification_event')]
