"""방 대화 API — 프론트 main2/src/api/index.ts 의 api.rooms.* 와 1:1.

    GET  /api/rooms/<room>/messages   그 방 메시지 → RoomMessage[] (room = all · design · front · back)
    POST /api/rooms/<room>/messages   메시지 보내기 → 201 RoomMessage (역할 방은 그 역할만, 아니면 403 room_read_only)
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import ProjectRole

from . import services
from .payloads import message_payload


class MessageInput(serializers.Serializer):
    """프론트 sendRoomMessage() 가 만드는 모양. author · time · attachments 는 서버가 정해요."""

    id = serializers.RegexField(r'^[A-Za-z0-9_-]{1,64}$')
    role = serializers.ChoiceField(choices=[k for k, _ in ProjectRole.ROLE_KEYS], required=False, allow_null=True)
    text = serializers.CharField(max_length=5000)
    ts = serializers.IntegerField(required=False, min_value=0)


class Messages(APIView):
    def get(self, request, room):
        _, messages = services.messages_in(request.user, room)
        return Response([message_payload(m, room) for m in messages])

    def post(self, request, room):
        s = MessageInput(data=request.data)
        s.is_valid(raise_exception=True)
        _, message = services.send(request.user, room, s.validated_data)
        return Response(message_payload(message, room), status=status.HTTP_201_CREATED)
