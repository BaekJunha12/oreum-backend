"""D. 방(역할 방 · 전체 방) · 대화 (docs/db/erd.sql).

rooms, room_messages, message_attachments, room_reads
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from handoffs.models import HandoffCard
from plans.models import Checkpoint
from projects.models import Project, ProjectRole

ATTACHMENT_TYPES = ['link', 'figma', 'pr', 'handoff']


class Room(models.Model):
    """방. 역할마다 하나(role 있음) + 전체 원정대 방 하나(role 없음).

    전체 방은 role_id 가 NULL 이라 UQ_room_role 로는 하나만 지켜지지 않아요 (MySQL 은 NULL 끼리 안 겹친다고 봐요).
    그래서 rooms.services.room_for 가 원정대 행을 잠그고 만들어요.
    """

    id = models.BigAutoField(primary_key=True, db_column='room_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='rooms')
    role = models.ForeignKey(ProjectRole, on_delete=models.CASCADE, null=True, blank=True, related_name='rooms')
    name = models.CharField('방 이름', max_length=50)
    ai_summary = models.CharField('AI 요약 한 줄', max_length=500, null=True, blank=True)
    summary_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rooms'
        verbose_name = verbose_name_plural = '방'
        constraints = [models.UniqueConstraint(fields=['project', 'role'], name='UQ_room_role')]

    def __str__(self):
        return self.name


class RoomMessage(models.Model):
    """방 대화 한 줄. id 는 프론트가 만들어 보내요 (보낸 즉시 화면에 그리기 때문)."""

    id = models.CharField(primary_key=True, max_length=64, db_column='message_id')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', db_column='author_user_id')
    author_role = models.ForeignKey(ProjectRole, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='author_role_id')
    body = models.TextField()
    is_notice = models.BooleanField('전체 방 공지', default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'room_messages'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['room', 'created_at'], name='IX_room_message_time')]


class MessageAttachment(models.Model):
    """메시지 첨부 (Figma 미리보기 · PR 카드 · 링크 칩 · 넘겨주기 배지). 서버가 만들어요 — 프론트는 보내지 않아요."""

    id = models.BigAutoField(primary_key=True, db_column='attachment_id')
    message = models.ForeignKey(RoomMessage, on_delete=models.CASCADE, related_name='attachments')
    type = models.CharField(max_length=10, choices=[(t, t) for t in ATTACHMENT_TYPES])
    source = models.CharField(max_length=10, null=True, blank=True)
    title = models.CharField(max_length=255)
    url = models.CharField(max_length=700, null=True, blank=True)
    version_label = models.CharField(max_length=50, null=True, blank=True)
    note = models.CharField(max_length=255, null=True, blank=True)
    path = models.CharField(max_length=255, null=True, blank=True)
    github_pr_id = models.BigIntegerField(null=True, blank=True)  # 2차: github_pull_requests 가 생기면 ForeignKey
    card = models.ForeignKey(HandoffCard, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'message_attachments'
        ordering = ['sort_order', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(type__in=ATTACHMENT_TYPES), name='CK_attachment_type')]


class RoomRead(models.Model):
    """방별 마지막으로 읽은 시각 (새 메시지 수). (room_id, user_id) 두 칸이 합쳐서 기본키예요."""

    pk = models.CompositePrimaryKey('room_id', 'user_id')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reads')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    last_read_at = models.DateTimeField()

    class Meta:
        db_table = 'room_reads'
