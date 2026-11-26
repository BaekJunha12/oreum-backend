"""A. 팀 스페이스 — workspaces, workspace_members (docs/db/erd.sql).

팀 스페이스 = 사이드바 맨 위에서 고르는 팀. 그 안에 원정대(projects)가 생겨요.
"""
from django.conf import settings
from django.db import models


class Workspace(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='workspace_id')
    name = models.CharField('팀 스페이스 이름', max_length=100)
    image_url = models.CharField('팀 스페이스 사진', max_length=500, null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='created_by', related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workspaces'
        verbose_name = verbose_name_plural = '팀 스페이스'

    def __str__(self):
        return self.name


class WorkspaceMember(models.Model):
    """팀 스페이스 ↔ 사용자. (workspace_id, user_id) 두 칸이 합쳐서 기본키예요."""

    OWNER, ADMIN, MEMBER = 'owner', 'admin', 'member'
    PERMISSION_ROLES = [(OWNER, '주인'), (ADMIN, '관리자'), (MEMBER, '멤버')]

    pk = models.CompositePrimaryKey('workspace_id', 'user_id')
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_memberships')
    permission_role = models.CharField(max_length=10, choices=PERMISSION_ROLES, default=MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workspace_members'
        verbose_name = verbose_name_plural = '팀 스페이스 멤버'
        constraints = [
            models.CheckConstraint(condition=models.Q(permission_role__in=['owner', 'admin', 'member']), name='CK_workspace_member_role'),
        ]
