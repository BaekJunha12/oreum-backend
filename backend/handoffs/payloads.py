"""요청 카드 모양 — 프론트 main2/src/data/requestStore.ts 의 HandoffCard · HistoryRecord 그대로 (+ 몇 칸 더)."""
from django.utils import timezone

from projects.payloads import iso

from . import dates


def role_ref(role):
    """카드의 fromRole · toRole: 기본 역할이면 'design' 같은 키, 직접 추가한 역할이면 역할 id."""
    if role is None:
        return None
    return role.role_key or str(role.pk)


def event_payload(event):
    """HistoryRecord { id, kind, author, role, at, ts, text, result? }."""
    out = {
        'id': event.id,
        'kind': event.kind,
        'author': event.author_user.name,
        'authorId': str(event.author_user_id),
        'role': role_ref(event.author_role),
        'at': dates.stamp(event.created_at),
        'ts': dates.millis(event.created_at),
        'text': event.text,
    }
    if event.result_title:
        out['result'] = event.result_title
    if event.result_url:
        out['resultUrl'] = event.result_url
    return out


def card_payload(card, people=None):
    """HandoffCard. people = {역할 id: 대표 이름} (목록에서 여러 번 찾지 않게 미리 계산해 둔 것)."""
    from .services import role_person

    people = people if people is not None else {}

    def person(user, role):
        if user is not None:
            return user.name
        if role.pk not in people:
            people[role.pk] = role_person(card.project, role)
        return people[role.pk]

    out = {
        'id': card.id,
        'title': card.title,
        'fromRole': role_ref(card.from_role),
        'toRole': role_ref(card.to_role),
        'maker': person(card.maker_user, card.from_role),
        'requester': person(card.requester_user, card.to_role),
        'origin': card.origin,
        'links': [link.title for link in card.links.all()],
        'description': card.description or '',
        'checkpoint': card.checkpoint.seq if card.checkpoint_id else 0,
        'due': card.due_label,
        'status': card.status,
        'history': [event_payload(e) for e in card.events.all()],
        # ↓ 프론트 타입에 없는 칸 (있으면 쓰고, 없어도 돼요)
        'dueAt': iso(card.due_at),
        'groupId': card.group_id,
        'createdAt': iso(card.created_at),
        'updatedAt': iso(card.updated_at),
        'fromRoleLabel': card.from_role.label,
        'toRoleLabel': card.to_role.label,
        'linkItems': [{'kind': link.kind, 'title': link.title, 'url': link.url} for link in card.links.all()],
    }
    if card.proposed_due_label:
        out['proposedDue'] = card.proposed_due_label
    if card.blocked_since:
        out['blocked'] = {'since': dates.day_stamp(card.blocked_since)}
        if card.blocked_reason:
            out['blocked']['reason'] = card.blocked_reason
        out['blockedDays'] = max(1, (timezone.localdate() - card.blocked_since).days + 1)
    if card.tag:
        out['tag'] = card.tag
    if card.is_auto:
        out['auto'] = True
    if card.review_path:
        out['reviewPath'] = card.review_path
    if card.github_pr_id:
        out['githubPrId'] = str(card.github_pr_id)
    return out


def cards_payload(cards):
    people = {}
    return [card_payload(c, people) for c in cards]
