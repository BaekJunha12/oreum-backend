"""방 대화 모양 — 프론트 main2/src/data/roomStore.ts 의 RoomMessage · pages/rooms/roomData.ts 의 Attachment."""
from django.utils import timezone

from handoffs import dates
from handoffs.payloads import role_ref
from projects.payloads import iso

from .services import can_write, open_cards, unread_count

STAGES = ['작업', '리뷰', '병합', '배포']
STAGE_INDEX = {'work': 0, 'review': 1, 'merged': 2, 'deployed': 3}


def attachment_payload(a):
    if a.type == 'link':
        out = {'type': 'link', 'source': a.source or 'GITHUB', 'title': a.title}
        if a.note:
            out['stages'] = a.note.split(',')
        if a.url:
            out['to'] = a.url
        return out
    if a.type == 'figma':
        return {'type': 'figma', 'thumb': 'mypage' if '마이' in a.title else 'login', 'note': a.note or '', 'version': a.version_label or '',
                'title': a.title, 'path': a.path or '', 'external': bool(a.url), **({'url': a.url} if a.url else {})}
    if a.type == 'pr':
        done = STAGE_INDEX.get(a.github_pr.stage, -1) if a.github_pr_id else -1
        stages = [{'label': s, 'state': 'done' if i <= done else ('current' if i == done + 1 else 'todo')} for i, s in enumerate(STAGES)]
        badge = {'tone': a.source if a.source in ('auto', 'blocked') else 'auto', 'label': a.version_label or '', 'text': a.note or '', 'to': a.url or ''}
        if a.card_id:
            badge['requestId'] = a.card_id
        return {'type': 'pr', 'title': a.title, 'branch': a.path or '', 'stages': stages, 'badge': badge}
    out = {'type': 'handoff', 'strong': a.title, 'rest': a.note or '', 'to': a.url or (f'/requests/{a.card_id}' if a.card_id else '')}
    if a.card_id:
        out['requestId'] = a.card_id
    return out


def message_payload(m):
    """RoomMessage { id, room, author, role, text, time, ts, attachments? } + 구간 · 공지."""
    local = timezone.localtime(m.created_at)
    out = {
        'id': m.id,
        'room': m.room.key,
        'author': m.author_user.name,
        'authorId': str(m.author_user_id),
        'role': role_ref(m.author_role) or 'design',
        'text': m.body,
        'time': local.strftime('%H:%M'),
        'ts': dates.millis(m.created_at),
        'checkpoint': m.checkpoint.seq if m.checkpoint_id else None,
        'notice': m.is_notice,
    }
    atts = [attachment_payload(a) for a in m.attachments.all()]
    if atts:
        out['attachments'] = atts
    return out


def room_payload(room, user, member=None):
    last = room.messages.select_related('author_user').order_by('-created_at').first()
    return {
        'id': room.key,
        'roomId': str(room.pk),
        'name': room.name,
        'role': role_ref(room.role) if room.role_id else None,
        'canWrite': can_write(user, room, member),
        'unread': unread_count(user, room),
        'openCards': open_cards(room).count(),
        'summary': room.ai_summary,
        'summaryUpdatedAt': iso(room.summary_updated_at),
        'lastMessage': {'author': last.author_user.name, 'text': last.body, 'ts': dates.millis(last.created_at)} if last else None,
    }
