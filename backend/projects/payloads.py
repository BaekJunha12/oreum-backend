"""원정대 API 가 돌려주는 모양. 프론트 타입처럼 id 는 글자, 칸 이름은 camelCase 예요."""
from django.utils import timezone

from .models import ProjectInvitation
from .services import invitation_roles, is_leader, roles_of


def iso(dt):
    return timezone.localtime(dt).isoformat() if dt else None


def role_payload(role):
    """프론트 PlanRole { id, label, people, role? } 과 같은 모양 (role = design · front · back, 직접 추가한 역할은 없음)."""
    out = {'id': str(role.pk), 'label': role.label, 'people': role.headcount}
    if role.role_key:
        out['role'] = role.role_key
    return out


def member_payload(member):
    return {
        'id': str(member.pk),
        'userId': str(member.user_id),
        'name': member.user.name,
        'email': member.user.email,
        'isLeader': member.is_leader,
        'roles': [role_payload(r) for r in roles_of(member)],
        'joinedAt': iso(member.joined_at),
    }


def invitation_payload(invitation):
    return {
        'id': str(invitation.pk),
        'token': invitation.token,
        'email': invitation.email,
        'status': invitation.status,
        'roles': [role_payload(r) for r in invitation_roles(invitation)],
        'invitedBy': {'id': str(invitation.invited_by_id), 'name': invitation.invited_by.name},
        'expiresAt': iso(invitation.expires_at),
        'createdAt': iso(invitation.created_at),
    }


def project_summary(project, member=None):
    """목록용 (원정대원 · 초대 없이)."""
    out = {
        'id': str(project.pk),
        'workspaceId': str(project.workspace_id),
        'name': project.name,
        'deadlineAt': iso(project.deadline_at),
        'scheduleUnit': project.schedule_unit,
        'status': project.status,
        'recommendAllTasks': project.recommend_all_tasks,
        'startedAt': iso(project.started_at),
        'completedAt': iso(project.completed_at),
        'roles': [role_payload(r) for r in project.roles.all()],
    }
    if member is not None:
        out['isLeader'] = member.is_leader
        out['myRoles'] = [str(r.pk) for r in roles_of(member)]
    return out


def project_detail(project, user):
    """상세: 원정대원 전체 + (리더에게만) 초대 대기 목록."""
    members = project.members.select_related('user').order_by('-is_leader', 'joined_at', 'id')
    me = next((m for m in members if m.user_id == user.pk), None)
    out = project_summary(project, me)
    out['members'] = [member_payload(m) for m in members]
    if is_leader(user, project):
        pending = project.invitations.filter(status=ProjectInvitation.PENDING).select_related('invited_by').order_by('-created_at')
        out['invitations'] = [invitation_payload(i) for i in pending]
    return out


def invitation_preview(invitation):
    """초대 링크를 연 사람에게 보여 줄 것 (토큰은 다시 보내지 않음)."""
    return {
        'project': {'id': str(invitation.project_id), 'name': invitation.project.name},
        'invitedBy': {'name': invitation.invited_by.name},
        'email': invitation.email,
        'status': invitation.status,
        'roles': [role_payload(r) for r in invitation_roles(invitation)],
        'expiresAt': iso(invitation.expires_at),
    }


def retrospective_payload(retro):
    return {
        'id': str(retro.pk),
        'author': {'id': str(retro.author_user_id), 'name': retro.author_user.name},
        'body': retro.body,
        'createdAt': iso(retro.created_at),
    }
