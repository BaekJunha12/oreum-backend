"""팀 스페이스 API — 프론트 api.workspaces.*

    GET  /api/workspaces           → 200 Workspace[] { id, name }   (내가 들어가 있는 것만)
    POST /api/workspaces  { name } → 201 Workspace                  (프론트 "팀 스페이스 추가하기" 버튼 자리)
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import create_workspace, workspaces_of


def workspace_payload(workspace):
    return {'id': str(workspace.pk), 'name': workspace.name}


class CreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    image_url = serializers.CharField(max_length=500, required=False, allow_blank=True)


class Workspaces(APIView):
    def get(self, request):
        return Response([workspace_payload(w) for w in workspaces_of(request.user)])

    def post(self, request):
        s = CreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        workspace = create_workspace(request.user, s.validated_data['name'], s.validated_data.get('image_url') or None)
        return Response(workspace_payload(workspace), status=status.HTTP_201_CREATED)
