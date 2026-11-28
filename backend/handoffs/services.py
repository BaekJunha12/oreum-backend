"""넘겨주기 카드 규칙. 다른 앱(알림 · 방)도 카드 표를 직접 고치지 말고 이 함수들을 불러요.

    cards_for(user)                       지금 원정대의 카드 목록 (원정대가 없으면 빈 목록)
    create_card(user, data)               새 카드 (data = CardInput 검사를 통과한 값)
    update_card(user, card_id, action, data)   수락 · 제안 · 전달 · 확인 · 수정 요청 · 막힘 · 코멘트
    card_created / events_added           카드 · 기록이 생길 때 보내는 신호 (알림 앱이 받아요)

프론트(requestStore.ts)는 한 일(action)과 그 결과로 계산한 카드(card)를 같이 보내요.
서버는 action 이 지금 상태에서 할 수 있는 일인지, 결과 상태가 맞는지만 확인하고 카드 값을 저장해요.
기록(history)은 늘어나기만 해요: 이미 있는 기록은 고치지 않고, 새 id 의 기록만 더해요.
"""
import re
from datetime import datetime

import django.dispatch
from django.db import transaction
from django.utils import timezone

from plans.services import checkpoint_by_seq, current_checkpoint
from projects.errors import Conflict, Forbidden, NotFound
from projects.models import ProjectRole
from projects.services import current_membership

from .models import STATUSES, CardEvent, CardLink, HandoffCard

card_created = django.dispatch.Signal()  # sender=HandoffCard, card
events_added = django.dispatch.Signal()  # sender=CardEvent, card, events

# 한 일(action) → (할 수 있는 지금 상태, 끝난 뒤 상태). None = 상태가 그대로
TRANSITIONS = {
    'accept': ({'requested'}, 'accepted'),
    'propose': ({'requested'}, None),
    'acceptProposed': ({'requested'}, 'accepted'),
    'deliver': ({'requested', 'accepted'}, 'delivered'),
    'confirm': ({'delivered'}, 'confirmed'),
    'fix': ({'delivered'}, 'accepted'),
    'block': ({'accepted'}, None),
    'unblock': (set(STATUSES), None),
    'comment': (set(STATUSES), None),
}
STALE = '카드가 그 사이에 바뀌었어요. 새로고침한 뒤 다시 해 주세요'


# ───────── 날짜 글자 ─────────

def parse_when(text, today=None):
    """'11/21 (금) 18:00' · '오늘 18:00' · '내일' · '11/20' → 시각. 날짜가 없는 글자('체크포인트 2')는 None.

    프론트 parseWhen 과 같은 규칙이에요 (연도는 올해). 정렬 · 마감 임박 계산용이고, 화면에는 글자(due_label)를 그대로 보여 줘요.
    """
    today = today or timezone.localdate()
    md = re.search(r'(\d{1,2})\s*/\s*(\d{1,2})', text or '')
    hm = re.search(r'(\d{1,2}):(\d{2})', text or '')
    if md:
        day = (int(md.group(1)), int(md.group(2)))
    elif '내일' in (text or ''):
        d = today.fromordinal(today.toordinal() + 1)
        day = (d.month, d.day)
    elif '오늘' in (text or ''):
        day = (today.month, today.day)
    else:
        return None
    try:
        when = datetime(today.year, day[0], day[1], int(hm.group(1)) if hm else 0, int(hm.group(2)) if hm else 0)
    except ValueError:  # 13/40 같은 글자
        return None
    return timezone.make_aware(when)


def parse_day(text, today=None):
    """막힌 날 'MM/DD' → date (못 읽으면 오늘)."""
    when = parse_when(text, today)
    return when.date() if when else (today or timezone.localdate())


# ───────── 읽기 ─────────

def _scope(user):
    """지금 원정대와 내 원정대원 행. 원정대가 없으면 (None, None)."""
    member = current_membership(user)
    return (member.project, member) if member else (None, None)


def cards_for(user):
    project, _ = _scope(user)
    if project is None:
        return HandoffCard.objects.none()
    return (
        HandoffCard.objects.filter(project=project)
        .select_related('from_role', 'to_role', 'maker_user', 'requester_user', 'checkpoint')
        .prefetch_related('links', 'events__author_user', 'events__author_role')
    )


def card_for(user, card_id):
    """지금 원정대의 카드. 남의 원정대 카드는 있는지도 알려 주지 않고 404."""
    card = cards_for(user).filter(pk=card_id).first()
    if card is None:
        raise NotFound('카드를 찾을 수 없어요', code='card_not_found')
    return card


# ───────── 만들기 · 바꾸기 ─────────

def _roles(project):
    return {r.role_key: r for r in ProjectRole.objects.filter(project=project, role_key__isnull=False)}


def _role(roles, key):
    if key not in roles:
        raise NotFound('원정대에 그 역할이 없어요', code='role_not_found')
    return roles[key]


def _person(project, role, name, me):
    """화면 이름(maker · requester) → 사용자. 나이거나, 그 역할을 맡은 원정대원 중 이름이 같은 사람. 없으면 None(역할 자리)."""
    if name and name == me.name:
        return me
    if not name:
        return None
    member = project.members.filter(role_links__role=role, user__name=name).select_related('user').first()
    return member.user if member else None


def _apply_fields(card, data, user, roles):
    """프론트가 계산한 카드 값을 행에 옮겨요 (역할 · origin 은 만들 때만 정해요)."""
    project = card.project
    card.title = data['title']
    card.description = data.get('description') or None
    card.maker_user = _person(project, card.from_role, data.get('maker'), user)
    card.requester_user = _person(project, card.to_role, data.get('requester'), user)
    seq = data.get('checkpoint')
    card.checkpoint = (checkpoint_by_seq(project, seq) if seq is not None else None) or current_checkpoint(project)
    card.due_label = data['due']
    card.due_at = parse_when(data['due'])
    card.proposed_due_label = data.get('proposedDue') or None
    card.proposed_due_at = parse_when(card.proposed_due_label) if card.proposed_due_label else None
    card.status = data['status']
    blocked = data.get('blocked')
    card.blocked_since = parse_day(blocked['since']) if blocked else None
    card.blocked_reason = (blocked.get('reason') or None) if blocked else None
    card.tag = data.get('tag') or None
    card.review_path = data.get('reviewPath') or None
    if card.status == HandoffCard.CONFIRMED and card.confirmed_at is None:
        card.confirmed_at = timezone.now()
    elif card.status != HandoffCard.CONFIRMED:
        card.confirmed_at = None


def _replace_links(card, links):
    card.links.all().delete()
    CardLink.objects.bulk_create(
        CardLink(card=card, title=text[:255], url=text if text.startswith(('http://', 'https://')) else None, kind=_link_kind(text), sort_order=i)
        for i, text in enumerate(links)
    )


def _link_kind(text):
    lowered = text.lower()
    if 'figma.com' in lowered or lowered.startswith('figma'):
        return 'figma'
    if 'github.com' in lowered or re.search(r'\bpr\s*#\d+', lowered):
        return 'github'
    return 'other'


def _add_events(card, history, user, roles):
    """아직 없는 기록만 더해요. 기록한 사람은 요청을 보낸 사람(로그인한 사용자)이에요."""
    have = set(card.events.values_list('id', flat=True))
    fresh = []
    for record in history:
        event_id = f'{card.pk}:{record["id"]}'
        if event_id in have:
            continue
        ts = record.get('ts')
        fresh.append(CardEvent(
            id=event_id, card=card, kind=record['kind'], author_user=user, author_role=roles.get(record['role']),
            text=record['text'], result_title=record.get('result') or None,
            created_at=datetime.fromtimestamp(ts / 1000, tz=timezone.get_current_timezone()) if ts else timezone.now(),
        ))
    CardEvent.objects.bulk_create(fresh)
    return fresh


@transaction.atomic
def create_card(user, data):
    """새 카드. 같은 id 로 다시 보내면(재시도) 이미 만든 카드를 그대로 돌려줘요."""
    project, member = _scope(user)
    if project is None:
        raise NotFound('원정대가 없어요. 먼저 원정대를 만들거나 초대를 받아 주세요', code='no_project')
    existing = HandoffCard.objects.filter(pk=data['id']).first()
    if existing is not None:
        if existing.project_id != project.pk:
            raise Conflict('이미 있는 카드 id 예요', code='card_id_taken')
        return card_for(user, existing.pk)
    if not data['history']:
        raise Conflict('카드에 첫 기록(요청 · 전달)이 없어요', code='card_without_history')

    roles = _roles(project)
    card = HandoffCard(
        id=data['id'], project=project, origin=data['origin'], created_by=user,
        from_role=_role(roles, data['fromRole']), to_role=_role(roles, data['toRole']),
    )
    _apply_fields(card, data, user, roles)
    card.save()
    _replace_links(card, data.get('links', []))
    events = _add_events(card, data['history'], user, roles)
    card_created.send(sender=HandoffCard, card=card)
    events_added.send(sender=CardEvent, card=card, events=events)
    return card_for(user, card.pk)


@transaction.atomic
def update_card(user, card_id, action, data):
    """카드에 한 일을 저장해요. 지금 상태에서 할 수 없는 일이면 409 (다른 사람이 먼저 바꿨을 때)."""
    if data['id'] != card_id:
        raise Conflict('주소의 카드와 보낸 카드가 달라요', code='card_id_mismatch')
    card = card_for(user, card_id)
    card = HandoffCard.objects.select_for_update().get(pk=card.pk)  # 두 사람이 동시에 눌러도 하나씩
    if data['fromRole'] != card.from_role.role_key or data['toRole'] != card.to_role.role_key:
        raise Forbidden('보내는 역할 · 받는 역할은 바꿀 수 없어요', code='card_roles_fixed')

    kind = action['type']
    allowed, after = TRANSITIONS[kind]
    if card.status not in allowed:
        raise Conflict(STALE, code='card_conflict')
    if kind == 'block' and card.blocked_since is not None:
        raise Conflict(STALE, code='card_conflict')
    if kind == 'unblock' and card.blocked_since is None:
        raise Conflict(STALE, code='card_conflict')
    if data['status'] != (after or card.status):
        raise Conflict(STALE, code='card_conflict')

    roles = _roles(card.project)
    _apply_fields(card, data, user, roles)
    card.save()
    _replace_links(card, data.get('links', []))
    events = _add_events(card, data['history'], user, roles)
    events_added.send(sender=CardEvent, card=card, events=events)
    return card_for(user, card.pk)

