"""방 · 대화 규칙.

    ensure_rooms(project)           전체 방 + 역할마다 방 하나를 만들어 둠 (원정대 · 역할이 생길 때)
    room_by_key(project, key)       'all' · 'design' · 'front' · 'back' · 역할 id → 방
    can_write(user, room)           쓸 수 있는 방인지 — 전체 방 = 원정대원 누구나, 역할 방 = 그 역할을 맡은 사람만
                                    (팀 변경 11/26: 다른 역할의 방은 읽기만, 대신 요청보내기)
"""
import re
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from handoffs.models import HandoffCard
from plans.services import checkpoint_or_current
from projects.errors import Conflict, Forbidden, NotFound
from projects.models import ProjectRole
from projects.services import membership, roles_of

from .models import MessageAttachment, Room, RoomMessage, RoomRead

ALL_ROOM_NAME = '전체 원정대'


def ensure_rooms(project):
    Room.objects.get_or_create(project=project, role=None, defaults={'name': ALL_ROOM_NAME})
    for role in ProjectRole.objects.filter(project=project):
        room, created = Room.objects.get_or_create(project=project, role=role, defaults={'name': role.label})
        if not created and room.name != role.label:
            room.name = role.label
            room.save(update_fields=['name'])


def rooms_of(project):
    ensure_rooms(project)
    return Room.objects.filter(project=project).select_related('role').order_by('role__sort_order', 'id')


def room_by_key(project, key):
    ensure_rooms(project)
    qs = Room.objects.filter(project=project).select_related('role')
    if key == 'all':
        room = qs.filter(role__isnull=True).first()
    elif key.isdigit():
        room = qs.filter(role_id=int(key)).first()
    else:
        room = qs.filter(role__role_key=key).first()
    if room is None:
        raise NotFound('방을 찾을 수 없어요', code='room_not_found')
    return room


def can_write(user, room, member=None):
    member = member or membership(user, room.project)
    if member is None:
        return False
    if room.role_id is None:
        return True
    return room.role in roles_of(member)


def _author_role(member, room, wanted=None):
    mine = list(roles_of(member))
    if room.role_id and room.role in mine:
        return room.role
    for role in mine:
        if wanted and (role.role_key == wanted or str(role.pk) == str(wanted)):
            return role
    return mine[0] if mine else None


def messages_of(room, checkpoint_seq=None, after=None, limit=500):
    qs = RoomMessage.objects.filter(room=room).select_related('author_user', 'author_role', 'checkpoint').prefetch_related('attachments')
    if checkpoint_seq is not None:
        qs = qs.filter(checkpoint__seq=checkpoint_seq)
    if after is not None:
        qs = qs.filter(created_at__gt=after)
    return list(qs.order_by('-created_at', '-id')[:limit])[::-1]


@transaction.atomic
def send_message(user, room, data):
    member = membership(user, room.project)
    if member is None:
        raise Forbidden('원정대원만 대화할 수 있어요')
    if not can_write(user, room, member):
        raise Forbidden(f'{room.name} 방은 읽기만 할 수 있어요. 이 역할에 부탁할 일은 "요청보내기"로 보내 주세요', code='room_read_only')
    text = (data.get('text') or '').strip()
    if not text:
        raise Conflict('메시지를 적어 주세요', code='empty_message')
    message_id = str(data.get('id') or f'm{timezone.now().timestamp():.0f}{user.pk}')[:64]
    try:
        with transaction.atomic():
            message = RoomMessage.objects.create(
                id=message_id, room=room, author_user=user, author_role=_author_role(member, room, data.get('role')),
                checkpoint=checkpoint_or_current(room.project, data.get('checkpoint')), body=text,
                is_notice=bool(data.get('notice')) and room.role_id is None,
            )
    except IntegrityError:
        raise Conflict('이미 있는 메시지 id 예요', code='message_exists')
    save_attachments(message, data.get('attachments') or [])
    mark_read(user, room)
    refresh_summary(room)
    return message


def _card(project, card_id):
    return HandoffCard.objects.filter(project=project, pk=card_id).first() if card_id else None


def _pull(project, attachment):
    """PR 첨부 → 연결한 PR (prId, 아니면 제목의 '#24'). 단계 막대가 GitHub 단계를 따라가요."""
    from versions.models import GithubPullRequest

    qs = GithubPullRequest.objects.filter(repo__project=project)
    if str(attachment.get('prId') or '').isdigit():
        return qs.filter(pk=int(attachment['prId'])).first()
    found = re.search(r'#(\d+)', attachment.get('title') or '')
    return qs.filter(number=int(found.group(1))).order_by('-updated_at').first() if found else None


def save_attachments(message, items):
    project = message.room.project
    rows = []
    for i, a in enumerate(items[:10]):
        kind = a.get('type')
        if kind == 'link':
            row = dict(source=(a.get('source') or '')[:10] or None, title=a.get('title', ''), url=a.get('to'), note=','.join(a.get('stages') or []) or None)
        elif kind == 'figma':
            row = dict(source='FIGMA', title=a.get('title', ''), note=a.get('note'), version_label=a.get('version'), path=a.get('path'), url=a.get('url'))
        elif kind == 'pr':
            badge = a.get('badge') or {}
            row = dict(source=(badge.get('tone') or '')[:10] or None, title=a.get('title', ''), path=a.get('branch'), note=badge.get('text'),
                       version_label=badge.get('label'), url=badge.get('to'), card=_card(project, badge.get('requestId')),
                       github_pr=_pull(project, a))
        elif kind == 'handoff':
            row = dict(title=a.get('strong', ''), note=a.get('rest'), url=a.get('to'), card=_card(project, a.get('requestId')))
        else:
            continue
        row = {k: (v[:255] if isinstance(v, str) and k in ('title', 'note', 'path') else v) for k, v in row.items()}
        rows.append(MessageAttachment(message=message, type=kind, sort_order=i, **row))
    MessageAttachment.objects.bulk_create(rows)


def mark_read(user, room, when=None):
    RoomRead.objects.update_or_create(room=room, user=user, defaults={'last_read_at': when or timezone.now()})


def unread_count(user, room):
    read = RoomRead.objects.filter(room=room, user=user).values_list('last_read_at', flat=True).first()
    qs = RoomMessage.objects.filter(room=room).exclude(author_user=user)
    return qs.filter(created_at__gt=read).count() if read else qs.count()


def open_cards(room):
    qs = HandoffCard.objects.filter(project=room.project).exclude(status=HandoffCard.CONFIRMED)
    if room.role_id:
        qs = qs.filter(from_role=room.role) | qs.filter(to_role=room.role)
    return qs


def refresh_summary(room):
    """방 요약 한 줄 (메인보드 방 카드). AI 없이: 열린 요청 · 막힘 · 마지막 대화."""
    cards = open_cards(room)
    blocked = cards.filter(blocked_since__isnull=False).count()
    last = RoomMessage.objects.filter(room=room).order_by('-created_at').first()
    parts = [f'열린 요청 {cards.count()}개']
    if blocked:
        parts.append(f'막힘 {blocked}개')
    if last:
        parts.append(f'마지막: {last.author_user.name} "{last.body[:40]}"')
    room.ai_summary = ' · '.join(parts)[:500]
    room.summary_updated_at = timezone.now()
    room.save(update_fields=['ai_summary', 'summary_updated_at'])
    return room


def parse_after(value):
    """?after=<ms> 또는 ISO 시각 → datetime."""
    if not value:
        return None
    if value.isdigit():
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.get_current_timezone())
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
