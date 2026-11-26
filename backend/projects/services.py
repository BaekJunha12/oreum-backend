"""원정대 규칙. 다른 앱(기획안 · 카드 · 방 · 알림)도 원정대 표를 직접 고치지 말고 이 함수들을 불러요.

자주 쓸 것
    current_project(user)          지금 원정대 (프론트가 원정대 id 를 보내지 않아서 서버가 정함)
    membership(user, project)      원정대원 행 (없으면 None)
    role_keys(member)              맡은 기본 역할 ['design', ...]
    create_project(user, ...)      원정대 만들기 (만든 사람 = 리더)
"""
from django.db import transaction
from django.utils import timezone

from workspaces.services import add_member, is_member, personal_workspace

from .errors import Conflict, Forbidden, Gone, NotFound
from .models import InvitationRole, Project, ProjectInvitation, ProjectMember, ProjectMemberRole, ProjectRole

DEFAULT_ROLES = [
    {'role_key': ProjectRole.DESIGN, 'label': '디자인', 'headcount': 1},
    {'role_key': ProjectRole.FRONT, 'label': '프론트', 'headcount': 1},
    {'role_key': ProjectRole.BACK, 'label': '백', 'headcount': 1},
]


# ───────── 읽기 ─────────

def memberships_of(user):
    """내 원정대원 행들. 가장 최근에 들어간 것부터."""
    return ProjectMember.objects.filter(user=user).select_related('project').order_by('-joined_at', '-id')


def current_membership(user):
    """지금 원정대의 내 원정대원 행.

    프론트(main2)는 GET /plan · /requests 처럼 원정대 id 없이 불러요. 그래서 서버가
    "가장 최근에 들어간 원정대"를 지금 원정대로 봐요. 원정대 고르기 화면이 생기면 여기만 바꾸면 돼요.
    """
    return memberships_of(user).first()


def current_project(user):
    m = current_membership(user)
    return m.project if m else None


def membership(user, project):
    return ProjectMember.objects.filter(user=user, project=project).first()


def is_leader(user, project):
    return ProjectMember.objects.filter(user=user, project=project, is_leader=True).exists()


def roles_of(member):
    """원정대원이 맡은 역할 (보여 줄 순서대로)."""
    return ProjectRole.objects.filter(member_links__member=member).order_by('sort_order', 'id')


def role_keys(member):
    """맡은 기본 역할 키만 ['design', 'front'] (직접 추가한 역할은 빠짐)."""
    return [r.role_key for r in roles_of(member) if r.role_key]


def primary_role_key(user):
    """로그인 응답의 user.role — 지금 원정대에서 맡은 첫 기본 역할. 없으면 None."""
    m = current_membership(user)
    keys = role_keys(m) if m else []
    return keys[0] if keys else None


def project_for_member(user, project_id):
    """원정대원만 볼 수 있어요. 남의 원정대는 있는지도 알려 주지 않고 404."""
    m = ProjectMember.objects.filter(user=user, project_id=project_id).select_related('project').first()
    if m is None:
        raise NotFound('원정대를 찾을 수 없어요')
    return m.project, m


# ───────── 만들기 · 참여 ─────────

def _check_roles_belong(project, roles):
    if any(r.project_id != project.pk for r in roles):
        raise Conflict('다른 원정대의 역할이에요', code='role_not_in_project')


def assign_roles(member, roles):
    """원정대원에게 역할을 더해요 (이미 맡은 역할은 그대로)."""
    _check_roles_belong(member.project, roles)
    have = set(ProjectMemberRole.objects.filter(member=member).values_list('role_id', flat=True))
    ProjectMemberRole.objects.bulk_create([ProjectMemberRole(member=member, role=r) for r in roles if r.pk not in have])


@transaction.atomic
def create_project(user, *, name, deadline_at, workspace=None, schedule_unit=Project.DAY, roles=None, my_roles=()):
    """원정대 만들기. 만든 사람이 리더가 돼요.

    roles     [{'role_key': 'design' | None, 'label': '디자인', 'headcount': 2}, ...] — 없으면 디자인 · 프론트 · 백 1명씩
    my_roles  리더가 맡을 역할의 label 또는 role_key ['design', '기획']
    workspace 없으면 내 첫 팀 스페이스 (하나도 없으면 새로 만듦)
    """
    workspace = workspace or personal_workspace(user)
    if not is_member(user, workspace):
        raise Forbidden('이 팀 스페이스의 멤버가 아니에요')

    project = Project.objects.create(workspace=workspace, name=name, deadline_at=deadline_at, schedule_unit=schedule_unit, created_by=user)
    made = [
        ProjectRole.objects.create(project=project, role_key=r.get('role_key'), label=r['label'], headcount=r.get('headcount', 1), sort_order=i)
        for i, r in enumerate(roles if roles is not None else DEFAULT_ROLES)
    ]
    leader = ProjectMember.objects.create(project=project, user=user, is_leader=True)
    wanted = set(my_roles)
    assign_roles(leader, [r for r in made if r.label in wanted or (r.role_key and r.role_key in wanted)])
    return project


@transaction.atomic
def join_project(user, project, roles=()):
    """원정대에 들어가요 (팀 스페이스 멤버도 같이). 이미 원정대원이면 역할만 더해요."""
    add_member(project.workspace, user)
    member, _ = ProjectMember.objects.get_or_create(project=project, user=user)
    assign_roles(member, list(roles))
    return member


# ───────── 초대 ─────────

def _require_leader(user, project):
    if not is_leader(user, project):
        raise Forbidden('리더만 할 수 있어요', code='leader_only')


@transaction.atomic
def create_invitation(inviter, project, *, email=None, roles=()):
    """초대 만들기 (리더만). email 이 있으면 그 이메일로 로그인한 사람만, 없으면 링크를 가진 누구나 받을 수 있어요."""
    _require_leader(inviter, project)
    roles = list(roles)
    _check_roles_belong(project, roles)
    email = email.lower() if email else None
    if email and ProjectMember.objects.filter(project=project, user__email=email).exists():
        raise Conflict('이미 원정대에 있는 사람이에요', code='already_member')

    invitation = ProjectInvitation.objects.create(project=project, email=email, invited_by=inviter)
    InvitationRole.objects.bulk_create([InvitationRole(invitation=invitation, role=r) for r in roles])
    return invitation


def refresh_status(invitation):
    """기한이 지난 '초대 대기'는 '만료됨'으로 바꿔 둬요 (따로 도는 작업 없이 읽을 때 정리)."""
    if invitation.status == ProjectInvitation.PENDING and invitation.expires_at <= timezone.now():
        invitation.status = ProjectInvitation.EXPIRED
        invitation.save(update_fields=['status'])
    return invitation


def invitation_by_token(token):
    invitation = ProjectInvitation.objects.select_related('project', 'invited_by').filter(token=token).first()
    if invitation is None:
        raise NotFound('초대를 찾을 수 없어요', code='invitation_not_found')
    return refresh_status(invitation)


def invitation_roles(invitation):
    return ProjectRole.objects.filter(pk__in=InvitationRole.objects.filter(invitation=invitation).values('role_id')).order_by('sort_order', 'id')


def accept_invitation(token, user):
    """초대 받기 → 원정대원이 되고 초대에 적힌 역할을 맡아요. 같은 사람이 다시 눌러도 괜찮아요."""
    # 만료 표시는 먼저 저장해 둬요 (아래에서 오류가 나도 되돌려지지 않게)
    found = invitation_by_token(token)
    with transaction.atomic():
        # 두 사람이 동시에 같은 초대를 눌러도 한 명만 받도록 이 행을 잠가요
        invitation = refresh_status(ProjectInvitation.objects.select_for_update().get(pk=found.pk))
        return _accept_locked(invitation, user)


def _accept_locked(invitation, user):
    if invitation.status == ProjectInvitation.ACCEPTED:
        if invitation.accepted_by_id == user.pk:
            return membership(user, invitation.project)  # 두 번 눌러도 같은 결과
        raise Conflict('이미 사용된 초대예요', code='invitation_used')
    if invitation.status == ProjectInvitation.REVOKED:
        raise Gone('취소된 초대예요', code='invitation_revoked')
    if invitation.status == ProjectInvitation.EXPIRED:
        raise Gone('초대가 만료됐어요. 리더에게 다시 요청해 주세요', code='invitation_expired')
    if invitation.email and invitation.email != user.email:
        raise Forbidden(f'이 초대는 {invitation.email} 계정으로 로그인해야 받을 수 있어요', code='invitation_other_email')
    if membership(user, invitation.project):
        raise Conflict('이미 이 원정대에 있어요', code='already_member')  # 초대를 쓰지 않고 남겨 둠

    member = join_project(user, invitation.project, invitation_roles(invitation))
    # 초대 하나 = 한 사람 (ERD 의 accepted_by 가 한 칸). 링크 초대도 한 번 쓰면 끝나요.
    invitation.status = ProjectInvitation.ACCEPTED
    invitation.accepted_by = user
    invitation.save(update_fields=['status', 'accepted_by'])
    return member


@transaction.atomic
def revoke_invitation(user, invitation):
    _require_leader(user, invitation.project)
    if invitation.status != ProjectInvitation.PENDING:
        raise Conflict('초대 대기 중인 초대만 취소할 수 있어요', code='invitation_not_pending')
    invitation.status = ProjectInvitation.REVOKED
    invitation.save(update_fields=['status'])
    return invitation
