"""방 · 대화 규칙.

    room_for(project, key)          'all' · 'design' · 'front' · 'back' → 방 (없으면 만들어요)
    can_talk(member, room)          이 방에 말할 수 있는지
    messages_in(user, key)          지금 원정대의 그 방 메시지 (그 방에 쓴 것만 — 전체 방 글을 역할 방에 같이 보여 주는 건 프론트가 해요)
    send(user, key, data)           메시지 보내기

대화 권한 (팀 수정사항 11/26): 전체 방은 누구나, 역할 방은 그 역할을 맡은 사람만 말할 수 있어요.
다른 역할 방은 읽을 수만 있고, 부탁할 일은 "요청 보내기"(POST /requests)로 보내요.
"""
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from plans.services import current_checkpoint
from projects.errors import Conflict, Forbidden, NotFound
from projects.models import Project, ProjectRole
from projects.services import current_membership, roles_of

from .models import Room, RoomMessage

ALL = 'all'
ROOM_KEYS = [ALL] + [k for k, _ in ProjectRole.ROLE_KEYS]
ALL_ROOM_NAME = '전체 원정대'
READ_ONLY = '다른 역할의 방에는 대화할 수 없어요. 부탁할 일은 요청 보내기로 보내 주세요'


@transaction.atomic
def room_for(project, key):
    if key not in ROOM_KEYS:
        raise NotFound('방을 찾을 수 없어요', code='room_not_found')
    if key == ALL:
        Project.objects.select_for_update().get(pk=project.pk)  # 전체 방이 둘 생기지 않게 (role NULL 은 UNIQUE 로 못 막아요)
        room = Room.objects.filter(project=project, role__isnull=True).first()
        return room or Room.objects.create(project=project, role=None, name=ALL_ROOM_NAME)
    role = ProjectRole.objects.filter(project=project, role_key=key).first()
    if role is None:
        raise NotFound('원정대에 그 역할 방이 없어요', code='room_not_found')
    return Room.objects.get_or_create(project=project, role=role, defaults={'name': f'{role.label} 방'})[0]


def can_talk(member, room):
    return room.role_id is None or roles_of(member).filter(pk=room.role_id).exists()


def _scope(user):
    member = current_membership(user)
    if member is None:
        raise NotFound('원정대가 없어요. 먼저 원정대를 만들거나 초대를 받아 주세요', code='no_project')
    return member.project, member


def messages_in(user, key):
    project, _ = _scope(user)
    room = room_for(project, key)
    return room, room.messages.select_related('author_user', 'author_role')


@transaction.atomic
def send(user, key, data):
    project, member = _scope(user)
    room = room_for(project, key)
    if not can_talk(member, room):
        raise Forbidden(READ_ONLY, code='room_read_only')

    existing = RoomMessage.objects.filter(pk=data['id']).select_related('room').first()
    if existing is not None:  # 같은 메시지를 다시 보냄(재시도) — 내 것이면 그대로, 아니면 충돌
        if existing.room_id != room.pk or existing.author_user_id != user.pk:
            raise Conflict('이미 있는 메시지 id 예요', code='message_id_taken')
        return room, existing

    mine = list(roles_of(member))
    role = next((r for r in mine if r.role_key == data['role']), None) or next((r for r in mine if r.role_key), None)
    ts = data.get('ts')
    message = RoomMessage.objects.create(
        id=data['id'], room=room, author_user=user, author_role=role, body=data['text'],
        checkpoint=current_checkpoint(project),
        created_at=datetime.fromtimestamp(ts / 1000, tz=timezone.get_current_timezone()) if ts else timezone.now(),
    )
    return room, message
