"""방 API 가 돌려주는 모양 = 프론트 RoomMessage (main2/src/data/roomStore.ts) 그대로."""
from django.utils import timezone


def message_payload(message, key):
    """key = 주소의 방 ('all' · 'design' …). 첨부는 서버가 만드는 것이라 아직 없어요 (GitHub · Figma 연결 후)."""
    when = timezone.localtime(message.created_at)
    return {
        'id': message.pk,
        'room': key,
        'author': message.author_user.name,
        'role': message.author_role.role_key if message.author_role else None,
        'text': message.body,
        'time': when.strftime('%H:%M'),
        'ts': int(message.created_at.timestamp() * 1000),
    }
