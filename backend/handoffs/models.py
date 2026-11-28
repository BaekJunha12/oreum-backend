"""C. 넘겨주기 카드(요청) · 주고받은 기록 (docs/db/erd.sql).

handoff_cards, card_links, card_events
원정대 · 역할 · 구간 표는 projects · plans 앱 것이라 여기서는 가리키기만 해요.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from plans.models import Checkpoint
from projects.models import Project, ProjectRole

STATUSES = ['requested', 'accepted', 'delivered', 'confirmed']
LINK_KINDS = ['figma', 'prototype', 'github', 'api_doc', 'other']
EVENT_KINDS = ['request', 'accept', 'propose', 'question', 'comment', 'deliver', 'fix', 'redeliver', 'confirm', 'block', 'unblock']


class HandoffCard(models.Model):
    """넘겨주기 카드. 요청 → 수락 → 전달 → 확인 흐름이에요.

    id 는 프론트가 만들어 보내요 (보낸 직후 /requests/:id 로 이동하기 때문). 프론트 HandoffCard 와 1:1.
    """

    REQUESTED, ACCEPTED, DELIVERED, CONFIRMED = STATUSES
    STATUS_CHOICES = [(REQUESTED, '요청됨'), (ACCEPTED, '진행 중'), (DELIVERED, '확인 대기'), (CONFIRMED, '확인 완료')]
    REQUEST, HANDOFF = 'request', 'handoff'
    ORIGINS = [(REQUEST, '받는 쪽이 요청'), (HANDOFF, '보내는 쪽이 바로 넘김')]

    id = models.CharField(primary_key=True, max_length=64, db_column='card_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='handoff_cards')
    group_id = models.CharField('같이 보낸 요청 묶음', max_length=64, null=True, blank=True)
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='handoff_cards')
    title = models.CharField('항목 이름', max_length=255)
    from_role = models.ForeignKey(ProjectRole, on_delete=models.PROTECT, related_name='+', db_column='from_role_id')
    to_role = models.ForeignKey(ProjectRole, on_delete=models.PROTECT, related_name='+', db_column='to_role_id')
    maker_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='maker_user_id')
    requester_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='requester_user_id')
    origin = models.CharField(max_length=10, choices=ORIGINS)
    description = models.TextField(null=True, blank=True)
    due_at = models.DateTimeField('희망 마감', null=True, blank=True)
    due_label = models.CharField('희망 마감 글자', max_length=50)
    proposed_due_at = models.DateTimeField('제안한 날짜', null=True, blank=True)
    proposed_due_label = models.CharField('제안한 날짜 글자', max_length=50, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=REQUESTED)
    blocked_since = models.DateField('막힌 날', null=True, blank=True)
    blocked_reason = models.CharField('막힌 이유', max_length=255, null=True, blank=True)
    tag = models.CharField(max_length=50, null=True, blank=True)
    is_auto = models.BooleanField('GitHub 배포로 자동 전달', default=False)
    # 2차: github_pull_requests 표가 생기면 ForeignKey 로 바꿔요. 지금은 숫자만 담는 칸이에요.
    github_pr_id = models.BigIntegerField(null=True, blank=True)
    review_path = models.CharField('결과물 검토 화면 주소', max_length=255, null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'handoff_cards'
        verbose_name = verbose_name_plural = '넘겨주기 카드'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['project', 'status'], name='IX_card_project_status')]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=STATUSES), name='CK_card_status'),
            models.CheckConstraint(condition=models.Q(origin__in=['request', 'handoff']), name='CK_card_origin'),
        ]

    def __str__(self):
        return self.title


class CardLink(models.Model):
    """카드 참고 링크. 프론트 links: string[] 의 한 칸이에요 (주소 또는 이름)."""

    id = models.BigAutoField(primary_key=True, db_column='link_id')
    card = models.ForeignKey(HandoffCard, on_delete=models.CASCADE, related_name='links')
    kind = models.CharField(max_length=10, choices=[(k, k) for k in LINK_KINDS], default='other')
    title = models.CharField('보이는 이름', max_length=255)
    url = models.CharField(max_length=700, null=True, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'card_links'
        ordering = ['sort_order', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(kind__in=LINK_KINDS), name='CK_card_link_kind')]


class CardEvent(models.Model):
    """주고받은 기록 한 줄 (프론트 HistoryRecord). 알림도 이 기록에서 만들어져요.

    id = '카드id:기록id'. 프론트의 기록 id(h…)는 카드 안에서만 겹치지 않아서 카드 id 를 앞에 붙여 전체에서 하나로 만들어요.
    알림 id(프론트 Notification.id)도 같은 모양이에요.
    """

    id = models.CharField(primary_key=True, max_length=64, db_column='event_id')
    card = models.ForeignKey(HandoffCard, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=10, choices=[(k, k) for k in EVENT_KINDS])
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', db_column='author_user_id')
    author_role = models.ForeignKey(ProjectRole, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='author_role_id')
    text = models.TextField()
    result_title = models.CharField('전달한 결과물 이름', max_length=255, null=True, blank=True)
    result_url = models.CharField('전달한 결과물 주소', max_length=700, null=True, blank=True)
    created_at = models.DateTimeField('언제', default=timezone.now)  # 프론트가 보낸 ts 가 있으면 그 시각

    class Meta:
        db_table = 'card_events'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['card', 'created_at'], name='IX_card_event_time')]
        constraints = [models.CheckConstraint(condition=models.Q(kind__in=EVENT_KINDS), name='CK_card_event_kind')]

    @property
    def record_id(self):
        """프론트에 돌려줄 기록 id (카드 id 를 뗀 것)."""
        return self.id.split(':', 1)[1]
