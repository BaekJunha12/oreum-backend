"""D. 방 · 대화 — rooms, room_messages, message_attachments, room_reads (docs/db/erd.sql).

방 = 역할마다 하나(role 있음) + 전체 원정대 방 하나(role 없음).
팀 변경 11/26: 다른 역할의 방에는 대화를 쓸 수 없어요 (읽기만, 대신 요청보내기). 규칙은 services.can_write.
"""
from django.conf import settings
from django.db import models

from handoffs.models import HandoffCard
from plans.models import Checkpoint
from projects.models import Project, ProjectRole


class Room(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='room_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='rooms')
    role = models.ForeignKey(ProjectRole, on_delete=models.CASCADE, null=True, blank=True, related_name='rooms')
    name = models.CharField('방 이름', max_length=50)
    ai_summary = models.CharField('요약 한 줄', max_length=500, null=True, blank=True)
    summary_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rooms'
        verbose_name = verbose_name_plural = '방'
        constraints = [
            models.UniqueConstraint(fields=['project', 'role'], name='UQ_room_role'),
            # 전체 방(role 없음)도 원정대마다 하나 (NULL 은 UNIQUE 에 안 걸려서 따로 — docs/db/README.md)
            models.UniqueConstraint(fields=['project'], condition=models.Q(role__isnull=True), name='UQ_room_all'),
        ]

    def __str__(self):
        return self.name

    @property
    def key(self):
        """주소에 쓰는 방 이름: 'all' · 'design' · 'front' · 'back' (직접 추가한 역할은 역할 id)."""
        if self.role_id is None:
            return 'all'
        return self.role.role_key or str(self.role_id)


class RoomMessage(models.Model):
    id = models.CharField(primary_key=True, max_length=64, db_column='message_id')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='author_user_id', related_name='+')
    author_role = models.ForeignKey(ProjectRole, on_delete=models.SET_NULL, null=True, blank=True, db_column='author_role_id', related_name='+')
    body = models.TextField()
    is_notice = models.BooleanField('전체 방 공지', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'room_messages'
        verbose_name = verbose_name_plural = '방 대화'
        ordering = ['created_at', 'id']


class MessageAttachment(models.Model):
    LINK, FIGMA, PR, HANDOFF = 'link', 'figma', 'pr', 'handoff'
    TYPES = [(LINK, '링크 칩'), (FIGMA, 'Figma 미리보기'), (PR, 'PR 카드'), (HANDOFF, '요청 배지')]

    id = models.BigAutoField(primary_key=True, db_column='attachment_id')
    message = models.ForeignKey(RoomMessage, on_delete=models.CASCADE, related_name='attachments')
    type = models.CharField(max_length=10, choices=TYPES)
    source = models.CharField(max_length=10, null=True, blank=True)
    title = models.CharField(max_length=255)
    url = models.CharField(max_length=700, null=True, blank=True)
    version_label = models.CharField(max_length=50, null=True, blank=True)
    note = models.CharField(max_length=255, null=True, blank=True)
    path = models.CharField(max_length=255, null=True, blank=True)
    github_pr = models.ForeignKey('versions.GithubPullRequest', on_delete=models.SET_NULL, null=True, blank=True, db_column='github_pr_id', related_name='+')
    card = models.ForeignKey(HandoffCard, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'message_attachments'
        verbose_name = verbose_name_plural = '메시지 첨부'
        ordering = ['sort_order', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(type__in=['link', 'figma', 'pr', 'handoff']), name='CK_attachment_type')]


class RoomRead(models.Model):
    pk = models.CompositePrimaryKey('room_id', 'user_id')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reads')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    last_read_at = models.DateTimeField()

    class Meta:
        db_table = 'room_reads'
