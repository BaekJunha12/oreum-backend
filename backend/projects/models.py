"""B. 원정대 · 역할 · 원정대원 · 초대 (docs/db/erd.sql).

projects, project_roles, project_members, project_member_roles, project_invitations, invitation_roles
기획안 · 루트(plan_documents, checkpoints, checkpoint_tasks)는 다른 앱에서 이 표들을 가리켜요.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from workspaces.models import Workspace

INVITATION_DAYS = 7  # 초대 링크는 7일 동안 쓸 수 있어요


class Project(models.Model):
    """원정대(프로젝트). 시작하기 화면의 마감일 · 일정 단위를 가져요."""

    PLANNING, CLIMBING, COMPLETED = 'planning', 'climbing', 'completed'
    STATUSES = [(PLANNING, '루트 만드는 중'), (CLIMBING, '출발함'), (COMPLETED, '정상 도착')]
    DAY, HOUR = 'day', 'hour'
    UNITS = [(DAY, '일 단위'), (HOUR, '시간 단위')]

    id = models.BigAutoField(primary_key=True, db_column='project_id')
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField('프로젝트 이름', max_length=100)
    deadline_at = models.DateTimeField('최종 마감')
    schedule_unit = models.CharField('일정 단위', max_length=10, choices=UNITS, default=DAY)
    status = models.CharField(max_length=10, choices=STATUSES, default=PLANNING)
    route_source_signature = models.CharField('루트를 만든 기획안 표시', max_length=255, null=True, blank=True)
    recommend_all_tasks = models.BooleanField('전체 할 일 받기', default=False)
    started_at = models.DateTimeField('출발 시각', null=True, blank=True)
    completed_at = models.DateTimeField('정상 도착 시각', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='created_by', related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'
        verbose_name = verbose_name_plural = '원정대'
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['planning', 'climbing', 'completed']), name='CK_project_status'),
            models.CheckConstraint(condition=models.Q(schedule_unit__in=['day', 'hour']), name='CK_project_schedule_unit'),
        ]

    def __str__(self):
        return self.name


class ProjectRole(models.Model):
    """역할 자리. 기본 역할(디자인 · 프론트 · 백)은 role_key 가 있고, 직접 추가한 역할(기획 · QA)은 없어요."""

    DESIGN, FRONT, BACK = 'design', 'front', 'back'
    ROLE_KEYS = [(DESIGN, '디자인'), (FRONT, '프론트'), (BACK, '백')]

    id = models.BigAutoField(primary_key=True, db_column='role_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='roles')
    role_key = models.CharField(max_length=10, choices=ROLE_KEYS, null=True, blank=True)
    label = models.CharField('화면 이름', max_length=30)
    headcount = models.IntegerField('필요 인원', default=1)
    sort_order = models.IntegerField('보여 줄 순서', default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_roles'
        verbose_name = verbose_name_plural = '역할'
        ordering = ['sort_order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['project', 'label'], name='UQ_project_role_label'),
            # 디자인 · 프론트 · 백 방은 원정대마다 하나씩 (ERD 에 없는 규칙 — docs/db/README.md)
            models.UniqueConstraint(fields=['project', 'role_key'], condition=models.Q(role_key__isnull=False), name='UQ_project_role_key'),
            models.CheckConstraint(condition=models.Q(role_key__isnull=True) | models.Q(role_key__in=['design', 'front', 'back']), name='CK_project_role_key'),
            models.CheckConstraint(condition=models.Q(headcount__gte=0), name='CK_project_role_headcount'),
        ]

    def __str__(self):
        return self.label


class ProjectMember(models.Model):
    """원정대원. 한 사람이 역할을 여러 개 맡을 수 있어요 (project_member_roles)."""

    id = models.BigAutoField(primary_key=True, db_column='member_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_memberships')
    is_leader = models.BooleanField('리더', default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_members'
        verbose_name = verbose_name_plural = '원정대원'
        constraints = [models.UniqueConstraint(fields=['project', 'user'], name='UQ_project_member')]

    def __str__(self):
        return f'{self.user} @ {self.project}'


class ProjectMemberRole(models.Model):
    """원정대원 ↔ 역할. (member_id, role_id) 두 칸이 합쳐서 기본키예요."""

    pk = models.CompositePrimaryKey('member_id', 'role_id')
    member = models.ForeignKey(ProjectMember, on_delete=models.CASCADE, related_name='role_links')
    role = models.ForeignKey(ProjectRole, on_delete=models.CASCADE, related_name='member_links')

    class Meta:
        db_table = 'project_member_roles'


def new_invitation_token():
    return secrets.token_hex(32)  # 64글자, 추측할 수 없는 값


def invitation_expiry():
    return timezone.now() + timedelta(days=INVITATION_DAYS)


class ProjectInvitation(models.Model):
    """원정대 초대. 이메일 초대(email 있음)와 링크 초대(email 없음, 누구나 링크로 들어옴)."""

    PENDING, ACCEPTED, REVOKED, EXPIRED = 'pending', 'accepted', 'revoked', 'expired'
    STATUSES = [(PENDING, '초대 대기'), (ACCEPTED, '수락함'), (REVOKED, '취소함'), (EXPIRED, '만료됨')]

    id = models.BigAutoField(primary_key=True, db_column='invitation_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField('초대받는 이메일', max_length=255, null=True, blank=True)
    token = models.CharField('초대 링크 토큰', max_length=64, default=new_invitation_token)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='invited_by', related_name='+')
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, db_column='accepted_by', related_name='+')
    expires_at = models.DateTimeField(default=invitation_expiry)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_invitations'
        verbose_name = verbose_name_plural = '원정대 초대'
        constraints = [
            models.UniqueConstraint(fields=['token'], name='UQ_invitation_token'),
            models.CheckConstraint(condition=models.Q(status__in=['pending', 'accepted', 'revoked', 'expired']), name='CK_invitation_status'),
        ]


class InvitationRole(models.Model):
    """초대 ↔ 들어오면 맡길 역할. (invitation_id, role_id) 두 칸이 합쳐서 기본키예요."""

    pk = models.CompositePrimaryKey('invitation_id', 'role_id')
    invitation = models.ForeignKey(ProjectInvitation, on_delete=models.CASCADE, related_name='role_links')
    role = models.ForeignKey(ProjectRole, on_delete=models.CASCADE, related_name='+')

    class Meta:
        db_table = 'invitation_roles'


class Retrospective(models.Model):
    """G. 정상 도착 뒤 회고 한 편 (원정대원 누구나 여러 번 쓸 수 있어요)."""

    id = models.BigAutoField(primary_key=True, db_column='retrospective_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='retrospectives')
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='author_user_id', related_name='+')
    body = models.TextField('회고 내용')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'retrospectives'
        verbose_name = verbose_name_plural = '회고'
        ordering = ['created_at', 'id']
