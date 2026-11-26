"""알림 API — 프론트 api.notifications.*

    GET  /api/notifications                 내 알림 (새것부터, ?unread=1 안 읽은 것만, ?all=1 모든 원정대)   → Notification[]
    GET  /api/notifications/unread-count    { count } (사이드바 빨간 숫자)
    POST /api/notifications/read  { ids }   읽음 표시 (ids 가 없으면 모두) → 204
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.services import project_context

from . import services
from .payloads import notification_payload


class ReadInput(serializers.Serializer):
    ids = serializers.ListField(child=serializers.CharField(max_length=140), required=False, allow_null=True, max_length=1000)


def _scope(request):
    if request.query_params.get('all') in ('1', 'true'):
        return None
    project, _ = project_context(request, required=False)
    return project


class Notifications(APIView):
    def get(self, request):
        project = _scope(request)
        qs = services.for_user(request.user, project)
        if request.query_params.get('unread') in ('1', 'true'):
            qs = qs.filter(is_read=False)
        return Response([notification_payload(n) for n in qs[:300]])


class UnreadCount(APIView):
    def get(self, request):
        return Response({'count': services.for_user(request.user, _scope(request)).filter(is_read=False).count()})


class MarkRead(APIView):
    def post(self, request):
        s = ReadInput(data=request.data)
        s.is_valid(raise_exception=True)
        services.mark_read(request.user, s.validated_data.get('ids'))
        return Response(status=status.HTTP_204_NO_CONTENT)
