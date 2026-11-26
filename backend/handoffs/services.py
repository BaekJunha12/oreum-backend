"""요청 카드 규칙 — 요청 → 수락(진행) → 전달(확인 대기) → 확인 완료, 막힘 · 날짜 제안 · 수정 요청 · 코멘트.

프론트는 PATCH /requests/:id 에 { action, card } 를 같이 보내요. 서버는 card 를 그대로 믿지 않고
**action 을 직접 적용**해서 상태를 바꿔요 (지금 상태에서 할 수 없는 일이면 409). 프론트가 만든 기록 한 줄(id · 글)은
그대로 받아서 저장해요 — 그래야 화면의 기록 id 와 서버 기록 id 가 같아요.

누가 무엇을 할 수 있나 (리더는 모두 가능)
    만드는 쪽(fromRole 을 맡은 사람 · maker)  : accept · propose · deliver
    요청한 쪽(toRole 을 맡은 사람 · requester) : acceptProposed · confirm · fix · block · unblock
    원정대원 누구나                            : comment(코멘트 · 질문)

상태표
    requested ─accept/acceptProposed→ accepted ─deliver→ delivered ─confirm→ confirmed
        │                                ↑                  │
        └──────────── deliver ───────────┼──── fix ─────────┘
    block/unblock 은 accepted 에서만 (막힘은 전달 · 확인하면 풀려요)
"""
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from plans.services import checkpoint_or_current
from projects.errors import Conflict, Forbidden, NotFound
from projects.models import ProjectMember
from projects.services import is_leader, match_role, membership, roles_of

from . import dates
from .models import CardEvent, CardLink, HandoffCard

MAKER_ACTIONS = {'accept', 'propose', 'deliver'}
REQUESTER_ACTIONS = {'acceptProposed', 'confirm', 'fix', 'block', 'unblock'}
BAD_STATE = '지금 상태에서는 할 수 없어요'


def new_id(prefix):
    return f'{prefix}{secrets.token_hex(6)}'


# ───────── 읽기 ─────────

def cards_of(project):
    return (
        HandoffCard.objects.filter(project=project)
        .select_related('from_role', 'to_role', 'maker_user', 'requester_user', 'checkpoint')
        .prefetch_related('links', 'events__author_user', 'events__author_role')
    )


def card_for(user, project, card_id):
    card = cards_of(project).filter(pk=card_id).first()
    if card is None:
        raise NotFound('요청을 찾을 수 없어요', code='card_not_found')
    return card


def role_person(project, role):
    """역할 자리의 대표 이름 (담당자가 비어 있을 때 화면에 보여 줄 사람)."""
    m = ProjectMember.objects.filter(project=project, role_links__role=role).select_related('user').order_by('joined_at', 'id').first()
    return m.user.name if m else role.label


def find_user_by_name(project, name):
    if not name:
        return None
    m = ProjectMember.objects.filter(project=project, user__name=name).select_related('user').first()
    return m.user if m else None


# ───────── 권한 ─────────

def side_of(user, card):
    """이 사람이 카드에서 어느 쪽인지 → {'maker', 'requester'} 중 해당하는 것들 (리더는 둘 다)."""
    project = card.project
    if is_leader(user, project):
        return {'maker', 'requester'}
    m = membership(user, project)
    if m is None:
        return set()
    mine = {r.pk for r in roles_of(m)}
    sides = set()
    if card.maker_user_id == user.pk or card.from_role_id in mine:
        sides.add('maker')
    if card.requester_user_id == user.pk or card.to_role_id in mine:
        sides.add('requester')
    return sides


def _check_side(user, card, kind):
    sides = side_of(user, card)
    if kind in MAKER_ACTIONS and 'maker' not in sides:
        raise Forbidden(f'{card.from_role.label} 쪽(만드는 쪽)만 할 수 있어요', code='maker_only')
    if kind in REQUESTER_ACTIONS and 'requester' not in sides:
        raise Forbidden(f'{card.to_role.label} 쪽(요청한 쪽)만 할 수 있어요', code='requester_only')


def acting_role(user, project, *preferred):
    """기록에 남길 '어느 역할로' — 카드의 역할 중 내가 맡은 것 우선, 없으면 내 첫 역할."""
    m = membership(user, project)
    mine = list(roles_of(m)) if m else []
    for role in preferred:
        if role in mine:
            return role
    return mine[0] if mine else (preferred[0] if preferred else None)


# ───────── 기록 ─────────

def _client_record(client_card, kind, known_ids):
    """프론트가 보낸 card.history 에서 이번 일로 새로 생긴 기록 (서버에 없는 id, 같은 kind) — 없으면 {}."""
    for rec in reversed((client_card or {}).get('history') or []):
        if rec.get('id') and rec['id'] not in known_ids and rec.get('kind') == kind:
            return rec
    return {}


def add_event(card, user, kind, text, *, role=None, result_title=None, result_url=None, client=None):
    """기록 한 줄 → 알림도 같이 만들어요."""
    client = client or {}
    event_id = str(client.get('id') or new_id('h'))[:64]
    if CardEvent.objects.filter(pk=event_id).exists():
        event_id = new_id('h')  # 다른 카드와 id 가 겹치면 서버가 새로 정해요 (프론트는 돌려준 카드로 맞춰요)
    event = CardEvent.objects.create(
        id=event_id, card=card, kind=kind, author_user=user, author_role=role,
        text=(client.get('text') or text or '').strip() or text,
        result_title=client.get('result') or result_title, result_url=result_url,
        created_at=timezone.now(),
    )
    from notifications.services import notify_event

    notify_event(event)
    return event


# ───────── 만들기 ─────────

def _resolve_roles(project, data):
    from_role, to_role = match_role(project, data['fromRole']), match_role(project, data['toRole'])
    if from_role is None or to_role is None:
        raise NotFound('역할을 찾을 수 없어요', code='role_not_found')
    if from_role.pk == to_role.pk:
        raise Conflict('보내는 역할과 받는 역할이 같아요', code='same_role')
    return from_role, to_role


def _set_links(card, links):
    CardLink.objects.filter(card=card).delete()
    CardLink.objects.bulk_create([CardLink(card=card, kind=link_kind(t), title=t[:255], url=link_url(t), sort_order=i) for i, t in enumerate(links)])


def link_kind(text):
    low = text.lower()
    if 'figma' in low:
        return CardLink.FIGMA
    if 'github' in low or ' pr ' in f' {low} ' or 'pr #' in low:
        return CardLink.GITHUB
    if 'api' in low or '명세' in low:
        return CardLink.API_DOC
    if '프로토' in low or 'prototype' in low:
        return CardLink.PROTOTYPE
    return CardLink.OTHER


def link_url(text):
    for word in text.split():
        if word.startswith(('http://', 'https://')):
            return word[:700]
    return None


@transaction.atomic
def create_card(user, project, data):
    """새 카드 (POST /requests). data = 프론트 HandoffCard.

    origin=request → 상태 '요청됨' + 'request' 기록 (요청한 사람 = 나)
    origin=handoff → 상태 '전달됨' + 'deliver' 기록 (만든 사람 = 나) — 대화에서 바로 보내기 (요청보내기)
    같은 역할 방향 · 같은 이름으로 기다리던 카드가 있으면 새로 만들지 않고 그 카드를 전달해요 (프론트 handOff 와 같은 규칙).
    """
    if membership(user, project) is None:
        raise Forbidden('원정대원만 요청을 보낼 수 있어요')
    from_role, to_role = _resolve_roles(project, data)
    origin = data.get('origin') or HandoffCard.REQUEST
    first = ((data.get('history') or [None])[0]) or {}

    if origin == HandoffCard.HANDOFF:
        waiting = HandoffCard.objects.filter(
            project=project, from_role=from_role, to_role=to_role, title=data['title'].strip(),
            status__in=[HandoffCard.REQUESTED, HandoffCard.ACCEPTED],
        ).first()
        if waiting:
            link = (data.get('links') or [None])[0]
            return apply_action(user, waiting, {'type': 'deliver', 'note': first.get('text') or data['title'], 'link': link}, None), True

    card_id = str(data.get('id') or new_id('r'))
    if HandoffCard.objects.filter(pk=card_id).exists():
        raise Conflict('이미 있는 요청 id 예요', code='card_exists')

    due_label = (data.get('due') or '').strip() or '날짜 미정'
    maker = find_user_by_name(project, data.get('maker'))
    requester = find_user_by_name(project, data.get('requester'))
    if origin == HandoffCard.HANDOFF:
        maker = user
    else:
        requester = user
    status = HandoffCard.DELIVERED if origin == HandoffCard.HANDOFF else HandoffCard.REQUESTED
    try:
        with transaction.atomic():
            card = HandoffCard.objects.create(
                id=card_id, project=project, group_id=data.get('groupId') or None,
                checkpoint=checkpoint_or_current(project, data.get('checkpoint')),
                title=data['title'].strip(), from_role=from_role, to_role=to_role, maker_user=maker, requester_user=requester,
                origin=origin, description=data.get('description') or '', due_label=due_label[:50], due_at=dates.parse_when(due_label),
                status=status, tag=data.get('tag') or None, review_path=data.get('reviewPath') or None, created_by=user,
            )
    except IntegrityError:
        raise Conflict('이미 있는 요청 id 예요', code='card_exists')
    _set_links(card, data.get('links') or [])

    if origin == HandoffCard.HANDOFF:
        result = (data.get('links') or [card.title])[0]
        add_event(card, user, 'deliver', f'{result} · {dates.due_day(due_label)}까지 확인 부탁', role=acting_role(user, project, from_role),
                  result_title=result, result_url=link_url(result or ''), client=first if first.get('kind') == 'deliver' else None)
    else:
        add_event(card, user, 'request', f'{dates.due_day(due_label)}까지 {card.title} 요청', role=acting_role(user, project, to_role),
                  client=first if first.get('kind') == 'request' else None)
    return card, False


# ───────── 한 일 적용 (PATCH /requests/:id) ─────────

@transaction.atomic
def apply_action(user, card, action, client_card):
    card = HandoffCard.objects.select_for_update().select_related('project', 'from_role', 'to_role').get(pk=card.pk)
    kind = action['type']
    if membership(user, card.project) is None and not is_leader(user, card.project):
        raise Forbidden('원정대원만 할 수 있어요')
    _check_side(user, card, kind)
    known = set(card.events.values_list('id', flat=True))
    project = card.project
    maker_role = acting_role(user, project, card.from_role)
    requester_role = acting_role(user, project, card.to_role)
    rec = lambda k: _client_record(client_card, k, known)  # noqa: E731
    fields = ['updated_at']

    def change(**values):
        for k, v in values.items():
            setattr(card, k, v)
            fields.append(k)

    if kind == 'accept':
        _need(card.status == HandoffCard.REQUESTED)
        change(status=HandoffCard.ACCEPTED, proposed_due_label=None, proposed_due_at=None, maker_user=card.maker_user or user)
        text = f'{dates.due_short(card.due_label)}까지 하기로 함'
        event = ('accept', text, maker_role, {})
    elif kind == 'propose':
        _need(card.status == HandoffCard.REQUESTED)
        date = action['date'].strip()
        change(proposed_due_label=date[:50], proposed_due_at=dates.parse_when(date))
        event = ('propose', f'{dates.due_short(card.due_label)} 대신 {dates.due_short(date)} 제안', maker_role, {})
    elif kind == 'acceptProposed':
        _need(card.status == HandoffCard.REQUESTED and bool(card.proposed_due_label))
        proposed = card.proposed_due_label
        change(due_label=proposed, due_at=card.proposed_due_at, proposed_due_label=None, proposed_due_at=None, status=HandoffCard.ACCEPTED)
        event = ('accept', f'제안한 {dates.due_short(proposed)}까지로 정함', requester_role, {})
    elif kind == 'deliver':
        _need(card.status in (HandoffCard.REQUESTED, HandoffCard.ACCEPTED))
        again = card.events.filter(kind__in=['deliver', 'redeliver']).count()
        link = (action.get('link') or '').strip() or None
        result = ' '.join(link.split()) if link else f'{card.title} v{again + 1}'
        note = (action.get('note') or '').strip()
        change(status=HandoffCard.DELIVERED, blocked_since=None, blocked_reason=None, proposed_due_label=None, proposed_due_at=None,
               maker_user=card.maker_user or user)
        if link and not card.links.filter(title=link).exists():
            CardLink.objects.create(card=card, kind=link_kind(link), title=link[:255], url=link_url(link), sort_order=card.links.count())
        k = 'redeliver' if again else 'deliver'
        event = (k, result if not note or note == result else f'{result} · {note}', maker_role, {'result_title': result, 'result_url': link_url(link or '')})
    elif kind == 'confirm':
        _need(card.status == HandoffCard.DELIVERED)
        change(status=HandoffCard.CONFIRMED, confirmed_at=timezone.now(), blocked_since=None, blocked_reason=None)
        event = ('confirm', (action.get('text') or '').strip() or '확인했어요', requester_role, {})
    elif kind == 'fix':
        _need(card.status == HandoffCard.DELIVERED)
        text = (action.get('text') or '').strip()
        if not text:
            raise Conflict('무엇을 고쳐야 하는지 적어 주세요', code='fix_text_required')
        change(status=HandoffCard.ACCEPTED)
        event = ('fix', text, requester_role, {})
    elif kind == 'block':
        _need(card.status == HandoffCard.ACCEPTED and card.blocked_since is None)
        reason = (action.get('reason') or '').strip()
        change(blocked_since=timezone.localdate(), blocked_reason=reason[:255] or None)
        event = ('block', reason or '기다리느라 일이 멈췄어요', requester_role, {})
    elif kind == 'unblock':
        _need(card.blocked_since is not None)
        change(blocked_since=None, blocked_reason=None)
        event = ('unblock', '막힘을 풀었어요', requester_role, {})
    elif kind == 'comment':
        text = (action.get('text') or '').strip()
        if not text:
            raise Conflict('내용을 적어 주세요', code='comment_text_required')
        k = action.get('kind') if action.get('kind') in ('comment', 'question') else 'comment'
        event = (k, text, acting_role(user, project, card.from_role, card.to_role), {})
    else:
        raise Conflict('모르는 일이에요', code='unknown_action')

    card.save(update_fields=list(dict.fromkeys(fields)))
    k, text, role, extra = event
    add_event(card, user, k, text, role=role, client=rec(k), **extra)
    return card


def _need(ok):
    if not ok:
        raise Conflict(BAD_STATE, code='invalid_transition')


# ───────── 그 밖 ─────────

@transaction.atomic
def update_fields(user, card, data):
    """카드 내용 고치기 (이름 · 설명 · 마감 · 구간 · 링크 · 칩). 만든 사람 · 양쪽 담당 · 리더만."""
    if not side_of(user, card) and card.created_by_id != user.pk:
        raise Forbidden('이 요청의 담당자만 고칠 수 있어요')
    fields = ['updated_at']
    for key, attr in (('title', 'title'), ('description', 'description'), ('tag', 'tag'), ('reviewPath', 'review_path')):
        if key in data:
            setattr(card, attr, data[key] or ('' if attr in ('title', 'description') else None))
            fields.append(attr)
    if 'due' in data:
        card.due_label, card.due_at = data['due'][:50], dates.parse_when(data['due'])
        fields += ['due_label', 'due_at']
    if 'checkpoint' in data:
        card.checkpoint = checkpoint_or_current(card.project, data['checkpoint'])
        fields.append('checkpoint')
    card.save(update_fields=fields)
    if 'links' in data:
        _set_links(card, data['links'])
    return card


def delete_card(user, card):
    if card.created_by_id != user.pk and not is_leader(user, card.project):
        raise Forbidden('요청을 만든 사람이나 리더만 지울 수 있어요')
    card.delete()


# ───────── 예시 데이터 (POST /requests/reset, 개발용) ─────────

SEED = [
    # (id, 제목, 보내는 역할, 받는 역할, origin, 구간, 마감, 상태, 막힘 이유, 칩, 기록[(kind, 역할쪽, 글, 결과)])
    ('login-api', '로그인 API', 'back', 'front', 'request', 1, '11/17 18:00', 'accepted', '토큰 처리 문제로 하루 더 필요', None,
     [('request', 'to', '11/17까지 로그인 API 요청', None), ('accept', 'from', '11/17 18:00까지 하기로 함', None),
      ('block', 'to', '토큰 처리 문제로 하루 더 필요', None)]),
    ('login-v2', '로그인 화면 v2', 'design', 'front', 'handoff', 1, '11/19', 'delivered', None, None,
     [('deliver', 'from', 'Figma 로그인 화면 v2 · 버튼 높이 48로 수정', 'Figma 로그인 화면 v2')]),
    ('signup-spec', '회원가입 API 명세', 'back', 'front', 'handoff', 1, '11/19', 'delivered', None, None,
     [('deliver', 'from', '회원가입 API 명세 문서', '회원가입 API 명세 문서')]),
    ('icon-set', '아이콘 세트', 'design', 'front', 'request', 2, '체크포인트 2', 'accepted', None, None,
     [('request', 'to', '체크포인트 2까지 아이콘 세트 요청', None), ('accept', 'from', '체크포인트 2까지 하기로 함', None)]),
    ('main-impl', '메인 화면 구현', 'front', 'design', 'handoff', 2, '11/19', 'delivered', None, 'PR #24',
     [('deliver', 'from', 'PR #24 배포 완료 → 디자인에 검토 요청 (자동)', 'PR #24 메인 화면 레이아웃')]),
    ('api-test', 'API 연동 테스트', 'front', 'back', 'request', 1, '11/21', 'requested', None, None,
     [('request', 'to', '11/21까지 API 연동 테스트 요청', None)]),
]


@transaction.atomic
def reset_demo(user, project):
    """원정대의 카드를 지우고 예시 카드로 채워요 (리더 · DEBUG 서버만). id 는 원정대 번호를 붙여 다른 원정대와 안 겹치게."""
    from projects.services import require_leader

    require_leader(user, project)
    HandoffCard.objects.filter(project=project).delete()
    start = timezone.now() - timedelta(days=4)
    for n, (cid, title, frm, to, origin, seq, due, status, blocked, tag, history) in enumerate(SEED):
        from_role, to_role = match_role(project, frm), match_role(project, to)
        if from_role is None or to_role is None:
            continue
        card = HandoffCard.objects.create(
            id=f'p{project.pk}-{cid}', project=project, checkpoint=checkpoint_or_current(project, seq), title=title,
            from_role=from_role, to_role=to_role, origin=origin, due_label=due, due_at=dates.parse_when(due), status=status,
            blocked_since=timezone.localdate() - timedelta(days=1) if blocked else None, blocked_reason=blocked, tag=tag,
            is_auto=bool(tag), created_by=user, maker_user=find_user_by_name(project, role_person(project, from_role)),
            requester_user=find_user_by_name(project, role_person(project, to_role)),
        )
        for i, (kind, side, text, result) in enumerate(history):
            role = from_role if side == 'from' else to_role
            author = (card.maker_user if side == 'from' else card.requester_user) or user
            CardEvent.objects.create(id=f'p{project.pk}-{cid}-{i}', card=card, kind=kind, author_user=author, author_role=role,
                                     text=text, result_title=result, created_at=start + timedelta(hours=n * 6 + i))
    return cards_of(project)
