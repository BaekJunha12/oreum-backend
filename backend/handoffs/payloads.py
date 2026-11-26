"""카드 API 가 돌려주는 모양 = 프론트 HandoffCard (main2/src/data/requestStore.ts) 그대로."""
from django.utils import timezone

from projects.models import ProjectMember


def stamp(dt):
    """'11/18 11:00' — 프론트 기록의 at 과 같은 모양 (한국 시간)."""
    return timezone.localtime(dt).strftime('%m/%d %H:%M')


def role_people(project):
    """{ role_id: 그 역할을 맡은 첫 원정대원 이름 } — 담당자가 안 정해진 카드에 보여 줄 이름."""
    people = {}
    members = ProjectMember.objects.filter(project=project).select_related('user').prefetch_related('role_links').order_by('joined_at', 'id')
    for m in members:
        for link in m.role_links.all():
            people.setdefault(link.role_id, m.user.name)
    return people


def event_payload(event):
    out = {
        'id': event.record_id,
        'kind': event.kind,
        'author': event.author_user.name,
        'role': event.author_role.role_key if event.author_role else None,
        'at': stamp(event.created_at),
        'ts': int(event.created_at.timestamp() * 1000),
        'text': event.text,
    }
    if event.result_title:
        out['result'] = event.result_title
    return out


def card_payload(card, people=None):
    people = people if people is not None else role_people(card.project)

    def name(user, role):
        return user.name if user else people.get(role.pk, role.label)

    out = {
        'id': card.pk,
        'title': card.title,
        'fromRole': card.from_role.role_key,
        'toRole': card.to_role.role_key,
        'maker': name(card.maker_user, card.from_role),
        'requester': name(card.requester_user, card.to_role),
        'origin': card.origin,
        'links': [link.url or link.title for link in card.links.all()],
        'description': card.description or '',
        'checkpoint': card.checkpoint.seq if card.checkpoint else 0,
        'due': card.due_label,
        'status': card.status,
        'history': [event_payload(e) for e in card.events.all()],
    }
    if card.proposed_due_label:
        out['proposedDue'] = card.proposed_due_label
    if card.blocked_since:
        out['blocked'] = {'since': card.blocked_since.strftime('%m/%d')}
        if card.blocked_reason:
            out['blocked']['reason'] = card.blocked_reason
    if card.tag:
        out['tag'] = card.tag
    if card.is_auto:
        out['auto'] = True
    if card.review_path:
        out['reviewPath'] = card.review_path
    return out


def cards_payload(cards):
    cards = list(cards)
    people = role_people(cards[0].project) if cards else {}
    return [card_payload(c, people) for c in cards]
