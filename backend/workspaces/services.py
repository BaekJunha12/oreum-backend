"""팀 스페이스 규칙. 다른 앱(projects 등)도 모델을 직접 고치지 말고 이 함수들을 불러요."""
from django.db import transaction

from .models import Workspace, WorkspaceMember


def workspaces_of(user):
    """내가 들어가 있는 팀 스페이스. 먼저 들어간 순서 (프론트는 첫 번째를 기본으로 보여 줘요)."""
    return Workspace.objects.filter(memberships__user=user).order_by('memberships__joined_at', 'id')


def is_member(user, workspace):
    return WorkspaceMember.objects.filter(workspace=workspace, user=user).exists()


@transaction.atomic
def create_workspace(user, name, image_url=None):
    """팀 스페이스를 만들고, 만든 사람을 주인(owner)으로 넣어요."""
    workspace = Workspace.objects.create(name=name, image_url=image_url, created_by=user)
    WorkspaceMember.objects.create(workspace=workspace, user=user, permission_role=WorkspaceMember.OWNER)
    return workspace


def add_member(workspace, user, permission_role=WorkspaceMember.MEMBER):
    """이미 멤버면 그대로 두고, 아니면 넣어요 (원정대 초대를 수락할 때 불림)."""
    member, _ = WorkspaceMember.objects.get_or_create(workspace=workspace, user=user, defaults={'permission_role': permission_role})
    return member


def personal_workspace(user):
    """사용자의 첫 팀 스페이스. 하나도 없으면 'OOO의 스페이스' 를 만들어 줘요 (원정대를 만들 곳이 필요할 때)."""
    return workspaces_of(user).first() or create_workspace(user, f'{user.name}의 스페이스')
