"""기획안 · 루트 API 가 돌려주는 모양. 프론트 main2/src/data/planStore.ts 의 Plan 에 몇 칸을 더 얹었어요
(프론트는 모르는 칸을 무시해서, 더 줘도 안전해요)."""
from datetime import timedelta

from django.utils import timezone

from projects.payloads import iso, role_payload
from projects.services import is_leader

from . import schedule
from .models import PlanDocument
from .services import current_checkpoint, current_document, screens

EMPTY_DOCUMENT = '아직 기획 문서가 없어요'


def checkpoint_payload(cp, project, current=None):
    """PlanCheckpoint { id, name } + 번호 · 기간 · 남은 시간 · 상태."""
    state = 'done' if cp.completed_at else ('current' if current and cp.pk == current.pk else 'todo')
    return {
        'id': str(cp.pk),
        'name': cp.name,
        'seq': cp.seq,
        'source': cp.source,
        'orderReason': cp.order_reason,
        'startAt': iso(cp.start_at),
        'endAt': iso(cp.end_at),
        'range': schedule.range_label(cp.start_at, cp.end_at, project.schedule_unit),
        'remaining': schedule.remaining(cp.end_at, project.schedule_unit) if cp.end_at and not cp.completed_at else None,
        'arrivedAt': iso(cp.arrived_at),
        'completedAt': iso(cp.completed_at),
        'state': state,
    }


def default_plan():
    """원정대가 아직 없을 때 GET /plan (프론트 DEFAULT_PLAN 과 같은 기본값, 구간은 비어 있음)."""
    deadline = (timezone.localtime() + timedelta(days=14)).replace(hour=18, minute=0, second=0, microsecond=0)
    return {
        'unit': 'day',
        'date': deadline.date().isoformat(),
        'time': '18:00',
        'roles': [
            {'id': 'design', 'label': '디자인', 'people': 1, 'role': 'design'},
            {'id': 'front', 'label': '프론트', 'people': 1, 'role': 'front'},
            {'id': 'back', 'label': '백', 'people': 1, 'role': 'back'},
        ],
        'checkpoints': [],
        'projectId': None,
        'document': document_payload(None),
    }


def plan_payload(project, user=None):
    """프론트 Plan { unit, date, time, roles, checkpoints, generatedFrom? } + 원정대 정보."""
    deadline = timezone.localtime(project.deadline_at)
    current = current_checkpoint(project)
    base = project.checkpoints.filter(seq=0).first()
    out = {
        'unit': project.schedule_unit,
        'date': deadline.date().isoformat(),
        'time': deadline.strftime('%H:%M'),
        'roles': [role_payload(r) for r in project.roles.all()],
        'checkpoints': [checkpoint_payload(c, project, current) for c in screens(project)],
        'projectId': str(project.pk),
        'projectName': project.name,
        'status': project.status,
        'deadlineAt': iso(project.deadline_at),
        'remaining': schedule.remaining(project.deadline_at, project.schedule_unit),
        'baseCamp': checkpoint_payload(base, project, current) if base else None,
        'currentCheckpoint': current.seq,
        'recommendAllTasks': project.recommend_all_tasks,
        'document': document_payload(current_document(project)),
    }
    if project.route_source_signature:
        out['generatedFrom'] = project.route_source_signature
    if user is not None:
        out['canEdit'] = is_leader(user, project)
    return out


def plan_file_payload(doc):
    """프론트 PlanFile { id, name, size, type, pages, url? }. url = 원정대원만 받을 수 있는 내려받기 주소."""
    return {
        'id': str(doc.pk),
        'name': doc.file_name,
        'size': doc.file_size,
        'type': doc.mime_type,
        'pages': doc.page_count,
        'url': f'/api/files/plan/{doc.pk}',
    }


def document_payload(doc, with_text=True):
    """기획 문서 칸. 없으면 { exists: false, message: '아직 기획 문서가 없어요' } (팀 변경 11/26: 빈 상태 안내)."""
    if doc is None:
        return {'exists': False, 'message': EMPTY_DOCUMENT}
    out = {
        'exists': True,
        'id': str(doc.pk),
        'sourceType': doc.source_type,
        'name': doc.file_name or (doc.link_url if doc.source_type == PlanDocument.LINK else '직접 쓴 기획 문서'),
        'editable': True,
        'updatedAt': iso(doc.created_at),
        'updatedBy': {'id': str(doc.uploaded_by_id), 'name': doc.uploaded_by.name},
        'isCurrent': doc.is_current,
    }
    if doc.source_type == PlanDocument.FILE:
        out['file'] = plan_file_payload(doc)
    if doc.source_type == PlanDocument.LINK:
        out['url'] = doc.link_url
    if with_text:
        out['text'] = doc.text_content or ''
    return out


def task_payload(task):
    return {
        'id': str(task.pk),
        'checkpoint': task.checkpoint.seq,
        'role': task.role.role_key or str(task.role_id),
        'roleId': str(task.role_id),
        'roleLabel': task.role.label,
        'title': task.title,
        'reason': task.reason,
        'origin': task.origin,
        'state': task.state,
        'assignee': {'memberId': str(task.assignee_member_id), 'name': task.assignee_member.user.name} if task.assignee_member_id else None,
        'doneAt': iso(task.done_at),
        'createdAt': iso(task.created_at),
    }


def route_payload(project, user):
    """루트 상세 (GET /route): 일정 + 구간마다 역할별 할 일 + 진행률."""
    out = plan_payload(project, user)
    rows = [project.checkpoints.filter(seq=0).first(), *screens(project)]
    by_cp = {}
    for task in _tasks(project):
        by_cp.setdefault(task.checkpoint_id, []).append(task_payload(task))
    out['route'] = []
    current = current_checkpoint(project)
    for cp in filter(None, rows):
        tasks = by_cp.get(cp.pk, [])
        picked = [t for t in tasks if t['state'] in ('selected', 'done')]
        done = [t for t in picked if t['state'] == 'done']
        out['route'].append({
            **checkpoint_payload(cp, project, current),
            'tasks': tasks,
            'progress': {'done': len(done), 'total': len(picked)},
        })
    return out


def _tasks(project):
    from .models import CheckpointTask

    return CheckpointTask.objects.filter(checkpoint__project=project).select_related('checkpoint', 'role', 'assignee_member__user')
