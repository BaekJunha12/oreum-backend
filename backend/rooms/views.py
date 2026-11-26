"""방 대화 API — 프론트 api.rooms.*  (room = 'all' · 'design' · 'front' · 'back')

    GET  /api/rooms                         방 목록 (쓸 수 있는지 · 안 읽은 수 · 열린 요청 수 · 요약)
    GET  /api/rooms/<room>/messages         그 방에 쓴 메시지 (?checkpoint=2 구간별 · ?after=<ms> 그 뒤만)   → RoomMessage[]
    POST /api/rooms/<room>/messages         보내기 RoomMessage → RoomMessage (다른 역할의 방이면 403 room_read_only)
    POST /api/rooms/<room>/read             여기까지 읽음 → 204
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.services import project_context

from . import services
from .payloads import message_payload, room_payload


class MessageInput(serializers.Serializer):
    id = serializers.CharField(max_length=64, required=False)
    text = serializers.CharField(max_length=5000)
    role = serializers.CharField(max_length=64, required=False, allow_blank=True)
    checkpoint = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    notice = serializers.BooleanField(required=False, default=False)
    attachments = serializers.ListField(child=serializers.DictField(), required=False, default=list, max_length=10)


class Rooms(APIView):
    def get(self, request):
        project, member = project_context(request, required=False)
        if project is None:
            return Response([])
        return Response([room_payload(r, request.user, member) for r in services.rooms_of(project)])


class RoomMessages(APIView):
    def get(self, request, room_key):
        project, _ = project_context(request, required=False)
        if project is None:
            return Response([])
        room = services.room_by_key(project, room_key)
        q = request.query_params
        seq = int(q['checkpoint']) if q.get('checkpoint', '').isdigit() else None
        return Response([message_payload(m) for m in services.messages_of(room, seq, services.parse_after(q.get('after')))])

    def post(self, request, room_key):
        s = MessageInput(data=request.data)
        s.is_valid(raise_exception=True)
        project, _ = project_context(request)
        message = services.send_message(request.user, services.room_by_key(project, room_key), s.validated_data)
        return Response(message_payload(message), status=status.HTTP_201_CREATED)


class RoomRead(APIView):
    def post(self, request, room_key):
        project, _ = project_context(request)
        services.mark_read(request.user, services.room_by_key(project, room_key))
        return Response(status=status.HTTP_204_NO_CONTENT)
