"""E. 알림 — notifications (docs/db/erd.sql). 카드 기록 한 줄 → 받는 사람마다 한 줄."""
from django.conf import settings
from django.db import models

from handoffs.models import CardEvent, HandoffCard


class Notification(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='notification_id')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    card = models.ForeignKey(HandoffCard, on_delete=models.CASCADE, related_name='+')
    event = models.ForeignKey(CardEvent, on_delete=models.CASCADE, related_name='notifications')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = verbose_name_plural = '알림'
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['user', 'event'], name='UQ_notification_event')]
