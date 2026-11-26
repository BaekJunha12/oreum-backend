"""알림 API — 프론트 main2/src/api/index.ts 의 api.notifications.* 와 1:1.

    GET  /api/notifications        내 알림 → Notification[] (새것부터)
    POST /api/notifications/read   { ids } → 204 (내 알림만 읽음으로)
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .payloads import inbox_payload


class MarkReadInput(serializers.Serializer):
    ids = serializers.ListField(child=serializers.CharField(max_length=64), max_length=500)


class Notifications(APIView):
    def get(self, request):
        return Response(inbox_payload(services.inbox(request.user)))


class MarkRead(APIView):
    def post(self, request):
        s = MarkReadInput(data=request.data)
        s.is_valid(raise_exception=True)
        services.mark_read(request.user, s.validated_data['ids'])
        return Response(status=status.HTTP_204_NO_CONTENT)
