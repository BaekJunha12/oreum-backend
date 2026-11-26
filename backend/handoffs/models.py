"""C. 요청 카드(넘겨주기 카드) · 주고받은 기록 — handoff_cards, card_links, card_events (docs/db/erd.sql).

팀 변경 11/26: 화면 이름이 "넘겨주기" → "요청보내기" 로 바뀌었어요. 표 이름(handoff_cards)은 ERD 그대로 둬요.
카드 · 기록 id 는 프론트가 만들어 보내요 (보낸 직후 /requests/:id 로 이동해서).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from plans.models import Checkpoint
from projects.models import Project, ProjectRole


class HandoffCard(models.Model):
    REQUESTED, ACCEPTED, DELIVERED, CONFIRMED = 'requested', 'accepted', 'delivered', 'confirmed'
    STATUSES = [(REQUESTED, '요청됨'), (ACCEPTED, '진행 중'), (DELIVERED, '확인 대기'), (CONFIRMED, '확인 완료')]
    REQUEST, HANDOFF = 'request', 'handoff'
    ORIGINS = [(REQUEST, '받는 쪽이 요청'), (HANDOFF, '보내는 쪽이 바로 보냄')]

    id = models.CharField(primary_key=True, max_length=64, db_column='card_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='cards')
    group_id = models.CharField('같이 보낸 요청 묶음', max_length=64, null=True, blank=True)
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='cards')
    title = models.CharField('항목 이름', max_length=255)
    from_role = models.ForeignKey(ProjectRole, on_delete=models.RESTRICT, db_column='from_role_id', related_name='+')
    to_role = models.ForeignKey(ProjectRole, on_delete=models.RESTRICT, db_column='to_role_id', related_name='+')
    maker_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, db_column='maker_user_id', related_name='+')
    requester_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, db_column='requester_user_id', related_name='+')
    origin = models.CharField(max_length=10, choices=ORIGINS)
    description = models.TextField(null=True, blank=True)
    due_at = models.DateTimeField('희망 마감', null=True, blank=True)
    due_label = models.CharField('희망 마감(화면 글자)', max_length=50)
    proposed_due_at = models.DateTimeField('제안한 날짜', null=True, blank=True)
    proposed_due_label = models.CharField('제안한 날짜(화면 글자)', max_length=50, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=REQUESTED)
    blocked_since = models.DateField('막힌 날', null=True, blank=True)
    blocked_reason = models.CharField('막힌 이유', max_length=255, null=True, blank=True)
    tag = models.CharField('작은 칩', max_length=50, null=True, blank=True)
    is_auto = models.BooleanField('GitHub 배포로 자동 전달', default=False)
    github_pr = models.ForeignKey('versions.GithubPullRequest', on_delete=models.SET_NULL, null=True, blank=True, db_column='github_pr_id', related_name='cards')
    review_path = models.CharField('결과물 검토 화면 주소', max_length=255, null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='created_by', related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'handoff_cards'
        verbose_name = verbose_name_plural = '요청 카드'
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['requested', 'accepted', 'delivered', 'confirmed']), name='CK_card_status'),
            models.CheckConstraint(condition=models.Q(origin__in=['request', 'handoff']), name='CK_card_origin'),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status != self.CONFIRMED


class CardLink(models.Model):
    FIGMA, PROTOTYPE, GITHUB, API_DOC, OTHER = 'figma', 'prototype', 'github', 'api_doc', 'other'
    KINDS = [(FIGMA, 'Figma'), (PROTOTYPE, '프로토타입'), (GITHUB, 'GitHub'), (API_DOC, 'API 문서'), (OTHER, '기타')]

    id = models.BigAutoField(primary_key=True, db_column='link_id')
    card = models.ForeignKey(HandoffCard, on_delete=models.CASCADE, related_name='links')
    kind = models.CharField(max_length=10, choices=KINDS, default=OTHER)
    title = models.CharField('보이는 이름', max_length=255)
    url = models.CharField(max_length=700, null=True, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'card_links'
        verbose_name = verbose_name_plural = '카드 링크'
        ordering = ['sort_order', 'id']


class CardEvent(models.Model):
    """주고받은 기록 한 줄 (알림도 여기서 만들어져요)."""

    KINDS = [(k, k) for k in ('request', 'accept', 'propose', 'question', 'comment', 'deliver', 'fix', 'redeliver', 'confirm', 'block', 'unblock')]

    id = models.CharField(primary_key=True, max_length=64, db_column='event_id')
    card = models.ForeignKey(HandoffCard, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=10, choices=KINDS)
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='author_user_id', related_name='+')
    author_role = models.ForeignKey(ProjectRole, on_delete=models.SET_NULL, null=True, blank=True, db_column='author_role_id', related_name='+')
    text = models.TextField()
    result_title = models.CharField('결과물 이름', max_length=255, null=True, blank=True)
    result_url = models.CharField('결과물 주소', max_length=700, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'card_events'
        verbose_name = verbose_name_plural = '주고받은 기록'
        ordering = ['created_at', 'id']
