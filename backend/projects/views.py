"""원정대 · 초대 API. 프론트에는 아직 화면이 없어서 모양은 임시예요 (화면이 생기면 맞춰요).

    GET  /api/projects                                   내 원정대 목록 (current: 지금 원정대)
    POST /api/projects                                   원정대 만들기 (만든 사람 = 리더)
    GET  /api/projects/<id>                              원정대 상세 (원정대원, 리더에게는 초대 대기 목록)
    POST /api/projects/<id>/invitations                  초대 만들기 (리더)
    POST /api/projects/<id>/invitations/<inv_id>/revoke  초대 취소 (리더)
    GET  /api/invitations/<token>                        초대 미리보기 (로그인 전에도)
    POST /api/invitations/<token>/accept                 초대 받기
    PATCH /api/projects/<id>                             설정 (리더): name · deadlineAt · scheduleUnit · recommendAllTasks
    GET  /api/projects/<id>/retrospectives               회고 목록
    POST /api/projects/<id>/retrospectives  { body }     회고 쓰기 (원정대원)
"""
from django.db import IntegrityError
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from workspaces.models import Workspace

from . import services
from .errors import Conflict, NotFound
from .models import Project, ProjectRole
from .payloads import invitation_payload, invitation_preview, member_payload, project_detail, project_summary, retrospective_payload


class RoleInput(serializers.Serializer):
    """프론트 PlanRole 과 같은 모양으로 받아요."""

    label = serializers.CharField(max_length=30)
    people = serializers.IntegerField(min_value=0, max_value=20, default=1)
    role = serializers.ChoiceField(choices=[k for k, _ in ProjectRole.ROLE_KEYS], required=False, allow_null=True)


class CreateProjectInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    deadlineAt = serializers.DateTimeField()
    scheduleUnit = serializers.ChoiceField(choices=[k for k, _ in Project.UNITS], default=Project.DAY)
    workspaceId = serializers.IntegerField(required=False)
    roles = RoleInput(many=True, required=False)
    myRoles = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate_roles(self, roles):
        labels = [r['label'] for r in roles]
        keys = [r['role'] for r in roles if r.get('role')]
        if len(set(labels)) != len(labels):
            raise serializers.ValidationError('역할 이름이 겹쳐요')
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError('디자인 · 프론트 · 백은 한 번씩만 넣을 수 있어요')
        return roles


class InvitationInput(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    roleIds = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)


class Projects(APIView):
    def get(self, request):
        current = services.current_membership(request.user)
        rows = []
        for m in services.memberships_of(request.user):
            row = project_summary(m.project, m)
            row['current'] = current is not None and m.pk == current.pk
            rows.append(row)
        return Response(rows)

    def post(self, request):
        s = CreateProjectInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        workspace = None
        if 'workspaceId' in d:
            workspace = Workspace.objects.filter(pk=d['workspaceId']).first()
            if workspace is None:
                raise NotFound('팀 스페이스를 찾을 수 없어요')
        roles = None
        if 'roles' in d:
            roles = [{'role_key': r.get('role'), 'label': r['label'], 'headcount': r['people']} for r in d['roles']]
        project = services.create_project(
            request.user, name=d['name'], deadline_at=d['deadlineAt'], schedule_unit=d['scheduleUnit'],
            workspace=workspace, roles=roles, my_roles=d['myRoles'],
        )
        return Response(project_detail(project, request.user), status=status.HTTP_201_CREATED)


class SettingsInput(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    deadlineAt = serializers.DateTimeField(required=False)
    scheduleUnit = serializers.ChoiceField(choices=[k for k, _ in Project.UNITS], required=False)
    recommendAllTasks = serializers.BooleanField(required=False)


class ProjectDetail(APIView):
    def get(self, request, project_id):
        project, _ = services.project_for_member(request.user, project_id)
        return Response(project_detail(project, request.user))

    def patch(self, request, project_id):
        project, _ = services.project_for_member(request.user, project_id)
        s = SettingsInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        services.update_settings(
            request.user, project, name=d.get('name'), deadline_at=d.get('deadlineAt'),
            schedule_unit=d.get('scheduleUnit'), recommend_all_tasks=d.get('recommendAllTasks'),
        )
        project.refresh_from_db()
        return Response(project_detail(project, request.user))


class RetrospectiveInput(serializers.Serializer):
    body = serializers.CharField(max_length=5000)


class Retrospectives(APIView):
    def get(self, request, project_id):
        project, _ = services.project_for_member(request.user, project_id)
        rows = project.retrospectives.select_related('author_user')
        return Response([retrospective_payload(r) for r in rows])

    def post(self, request, project_id):
        project, _ = services.project_for_member(request.user, project_id)
        s = RetrospectiveInput(data=request.data)
        s.is_valid(raise_exception=True)
        retro = services.add_retrospective(request.user, project, s.validated_data['body'])
        return Response(retrospective_payload(retro), status=status.HTTP_201_CREATED)


class Invitations(APIView):
    def post(self, request, project_id):
        project, _ = services.project_for_member(request.user, project_id)
        s = InvitationInput(data=request.data)
        s.is_valid(raise_exception=True)
        role_ids = s.validated_data['roleIds']
        roles = list(ProjectRole.objects.filter(pk__in=role_ids))
        if len(roles) != len(set(role_ids)):
            raise NotFound('역할을 찾을 수 없어요', code='role_not_found')
        invitation = services.create_invitation(request.user, project, email=s.validated_data.get('email') or None, roles=roles)
        return Response(invitation_payload(invitation), status=status.HTTP_201_CREATED)


class RevokeInvitation(APIView):
    def post(self, request, project_id, invitation_id):
        project, _ = services.project_for_member(request.user, project_id)
        invitation = project.invitations.filter(pk=invitation_id).select_related('project', 'invited_by').first()
        if invitation is None:
            raise NotFound('초대를 찾을 수 없어요', code='invitation_not_found')
        return Response(invitation_payload(services.revoke_invitation(request.user, invitation)))


class InvitationByToken(APIView):
    permission_classes = [AllowAny]  # 초대 링크를 열면 로그인 전에도 어느 원정대인지 보여 줘요

    def get(self, request, token):
        return Response(invitation_preview(services.invitation_by_token(token)))


class AcceptInvitation(APIView):
    def post(self, request, token):
        try:
            member = services.accept_invitation(token, request.user)
        except IntegrityError:  # 같은 사람이 동시에 두 번 눌렀을 때
            raise Conflict('이미 처리된 초대예요', code='invitation_used')
        return Response({'project': project_summary(member.project, member), 'member': member_payload(member)})
