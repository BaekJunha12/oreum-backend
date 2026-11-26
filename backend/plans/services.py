"""기획안 · 루트 규칙. 다른 앱(카드 · 방)도 구간 표를 직접 뒤지지 말고 이 함수들을 불러요.

자주 쓸 것
    current_checkpoint(project)        지금 구간 (새 카드 · 새 메시지의 기본 구간). 항상 구간 하나를 돌려줘요
    checkpoint_by_seq(project, seq)    프론트의 구간 번호(0 = 베이스 캠프)로 구간 찾기. 없으면 None

일정 (GET · PUT /plan)
    save_plan(user, project, ...)      마감 · 단위 · 역할 · 구간을 한 번에 저장 (리더만, 원정대가 없으면 만듦)

기획안 (POST /files/plan, GET · PUT · DELETE /plan/document)
    save_plan_file · save_plan_text · save_plan_link · clear_document

루트 진행 (POST /route/start, /checkpoints/<seq>/complete, /route/summit)
    start_route · complete_checkpoint · reach_summit
"""
import os
import uuid
from datetime import timedelta

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from projects.errors import Conflict, Forbidden, NotFound
from projects.models import Project
from projects.services import create_project, is_leader, membership, require_leader, roles_of, update_plan_settings

from . import recommend, schedule
from .models import BASE_CAMP_NAME, MAX_CHECKPOINTS, Checkpoint, CheckpointTask, PlanDocument

DEFAULT_PROJECT_NAME = '내 원정대'
MAX_PLAN_FILE_BYTES = 20 * 1024 * 1024  # 20MB
# 올릴 수 있는 기획안 파일 (프론트 StartPage 의 accept=".pdf,.md,.txt,image/*"). 확장자 → 저장할 MIME
PLAN_FILE_TYPES = {
    '.pdf': 'application/pdf',
    '.md': 'text/markdown',
    '.txt': 'text/plain',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}
TEXT_EXTENSIONS = ('.md', '.txt')
TEXT_LIMIT = 200_000  # 본문으로 저장할 글자 수


# ───────── 구간 찾기 ─────────

def ensure_base_camp(project):
    """베이스 캠프(0번 구간)는 원정대마다 항상 하나 (ERD)."""
    return Checkpoint.objects.get_or_create(project=project, seq=0, defaults={'name': BASE_CAMP_NAME})[0]


def screens(project):
    """화면 구간(1번부터) — 베이스 캠프 빼고."""
    return project.checkpoints.filter(seq__gte=1).order_by('seq')


def checkpoint_by_seq(project, seq):
    if seq is None:
        return None
    return project.checkpoints.filter(seq=seq).first()


def current_checkpoint(project):
    """지금 구간: 안 끝난 화면 구간 중 번호가 가장 작은 것 → 전부 끝났으면 마지막 → 화면 구간이 없으면 베이스 캠프."""
    rows = screens(project)
    return rows.filter(completed_at__isnull=True).first() or rows.last() or ensure_base_camp(project)


def checkpoint_or_current(project, seq):
    """프론트가 보낸 번호의 구간, 없거나 못 찾으면 지금 구간."""
    return checkpoint_by_seq(project, seq) or current_checkpoint(project)


# ───────── 일정 저장 (PUT /plan) ─────────

def project_for_edit(user, project, **create):
    """일정 · 기획안을 고칠 원정대 (리더만). 시작하기에서 원정대 없이 바로 저장하면 새로 만들어 줘요."""
    if project is None:
        roles = create.get('roles') or []
        if roles and not create.get('my_roles'):
            create['my_roles'] = [roles[0].get('role_key') or roles[0]['label']]  # 만든 사람은 첫 역할을 맡아요
        create.setdefault('name', DEFAULT_PROJECT_NAME)
        create.setdefault('deadline_at', (timezone.localtime() + timedelta(days=14)).replace(hour=18, minute=0, second=0, microsecond=0))
        return create_project(user, **create)
    require_leader(user, project)
    return project


def _role_rows(roles):
    """프론트 PlanRole[] → projects.services 가 받는 모양."""
    return [{'id': r.get('id'), 'label': r['label'], 'headcount': r.get('people', 1), 'role_key': r.get('role')} for r in roles]


@transaction.atomic
def save_plan(user, project, *, deadline_at, unit, roles, checkpoints, generated_from=None, name=None):
    """시작하기 화면의 일정을 한 번에 저장해요 (프론트 Plan 그대로).

    checkpoints = [{ id, name, startAt?, endAt? }] — 보낸 순서가 구간 순서(1번부터).
    """
    if len(checkpoints) > MAX_CHECKPOINTS:
        raise ValidationError({'checkpoints': [f'체크포인트는 최대 {MAX_CHECKPOINTS}개까지예요']})
    created = project is None
    project = project_for_edit(
        user, project, deadline_at=deadline_at, schedule_unit=unit,
        roles=[{'role_key': r.get('role'), 'label': r['label'], 'headcount': r.get('people', 1)} for r in roles],
    )
    old_deadline, old_unit = project.deadline_at, project.schedule_unit
    project = update_plan_settings(user, project, deadline_at=deadline_at, schedule_unit=unit, roles=None if created else _role_rows(roles), name=name)
    if generated_from is not None and project.route_source_signature != generated_from:
        project.route_source_signature = generated_from or None
        project.save(update_fields=['route_source_signature', 'updated_at'])

    shape_changed = sync_checkpoints(project, checkpoints)
    if shape_changed or old_deadline != project.deadline_at or old_unit != project.schedule_unit:
        reschedule(project)
    return project


def _pk(value):
    value = '' if value is None else str(value)
    return int(value) if value.isascii() and value.isdigit() else None


def sync_checkpoints(project, items):
    """화면 구간을 보낸 목록에 맞춰요. 구간이 바뀌었으면(개수 · 순서 · 새 구간) True.

    같은 구간을 찾는 순서: ① id 가 그 원정대의 구간 id 면 그 구간  ② 아니면 같은 자리(번호)의 남은 구간.
    (프론트는 추천 직후 'r1' 같은 임시 id 를 보내요 → 자리로 맞춰서, 저장할 때마다 구간이 새로 생기지 않게)
    빠진 구간은 지우고, 그 구간에 있던 카드 · 대화는 남은 마지막 구간으로 옮겨요 (구간을 지워도 기록은 남게).
    """
    existing = list(screens(project))
    by_pk = {c.pk: c for c in existing}
    used, matched = set(), []
    for item in items:
        cp = by_pk.get(_pk(item.get('id')))
        matched.append(cp if cp and cp.pk not in used else None)
        if matched[-1]:
            used.add(cp.pk)
    free = [c for c in existing if c.pk not in used]
    for i, cp in enumerate(matched):
        if cp is None:
            positional = next((c for c in free if c.seq == i + 1), None)
            if positional:
                matched[i] = positional
                free.remove(positional)
                used.add(positional.pk)

    gone = [c for c in existing if c.pk not in used]
    changed = bool(gone) or any(cp is None or cp.seq != i + 1 for i, cp in enumerate(matched))

    # 번호(seq)는 원정대 안에서 겹치면 안 돼서, 남길 구간을 먼저 음수 번호로 비켜 둬요
    for cp in matched:
        if cp:
            Checkpoint.objects.filter(pk=cp.pk).update(seq=-cp.pk)
    if gone:
        _move_records_off(project, gone, keep=[cp for cp in matched if cp])
        Checkpoint.objects.filter(pk__in=[c.pk for c in gone]).delete()

    for i, (item, cp) in enumerate(zip(items, matched), start=1):
        values = {'seq': i, 'name': item['name'].strip()}
        if item.get('startAt') or item.get('endAt'):
            values.update(start_at=item.get('startAt'), end_at=item.get('endAt'))
        if cp:
            Checkpoint.objects.filter(pk=cp.pk).update(**values, updated_at=timezone.now())
        else:
            Checkpoint.objects.create(project=project, source=item.get('source') or Checkpoint.MANUAL, **values)
    return changed


def _move_records_off(project, gone, keep):
    """지울 구간의 카드 · 대화를 남는 구간 중 마지막 것(없으면 베이스 캠프)으로 옮겨요."""
    from handoffs.models import HandoffCard
    from rooms.models import RoomMessage

    target = keep[-1] if keep else ensure_base_camp(project)
    ids = [c.pk for c in gone]
    HandoffCard.objects.filter(checkpoint_id__in=ids).update(checkpoint=target)
    RoomMessage.objects.filter(checkpoint_id__in=ids).update(checkpoint=target)


def reschedule(project, start=None):
    """화면 구간의 시작 · 목표를 schedule.spread 로 다시 나눠요 (직접 날짜를 넣은 구간도 덮어씀)."""
    rows = list(screens(project))
    start = start or project.started_at or None
    for cp, (begin, end) in zip(rows, schedule.spread(len(rows), project.deadline_at, project.schedule_unit, start)):
        Checkpoint.objects.filter(pk=cp.pk).update(start_at=begin, end_at=end)
    base = ensure_base_camp(project)
    if rows:
        first_start = Checkpoint.objects.get(pk=rows[0].pk).start_at
        Checkpoint.objects.filter(pk=base.pk).update(start_at=schedule.start_point(project.schedule_unit), end_at=first_start)


def set_checkpoint_dates(user, project, seq, start_at, end_at):
    """구간 하나의 날짜 · 시간만 고치기 (리더). '일 단위 → 날짜/시간 수정 가능하게' (팀 변경 11/26)."""
    require_leader(user, project)
    cp = checkpoint_by_seq(project, seq)
    if cp is None:
        raise NotFound('구간을 찾을 수 없어요', code='checkpoint_not_found')
    if start_at and end_at and end_at < start_at:
        raise ValidationError({'endAt': ['목표가 시작보다 앞이에요']})
    if end_at and end_at > project.deadline_at:
        raise ValidationError({'endAt': ['목표가 최종 마감보다 늦어요']})
    cp.start_at, cp.end_at = start_at, end_at
    cp.save(update_fields=['start_at', 'end_at', 'updated_at'])
    return cp


# ───────── 기획안 ─────────

def current_document(project):
    return project.plan_documents.filter(is_current=True).first() if project else None


@transaction.atomic
def set_current_document(project, user, **fields):
    """지금 쓰는 기획안을 바꿔요. 이전 것은 지우지 않고 is_current 만 꺼요 (편집 기록)."""
    Project.objects.select_for_update().get(pk=project.pk)  # 같은 원정대에 동시에 올려도 현재 기획안은 하나만
    PlanDocument.objects.filter(project=project, is_current=True).update(is_current=False)
    return PlanDocument.objects.create(project=project, uploaded_by=user, is_current=True, **fields)


def check_plan_file(upload):
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in PLAN_FILE_TYPES:
        raise ValidationError('지원하지 않는 파일이에요. pdf · md · txt · 이미지(png, jpg, gif, webp)만 올릴 수 있어요')
    if upload.size == 0:
        raise ValidationError('빈 파일이에요')
    if upload.size > MAX_PLAN_FILE_BYTES:
        raise ValidationError(f'파일이 너무 커요 (최대 {MAX_PLAN_FILE_BYTES // 1024 // 1024}MB)')
    return ext


def _pdf_pages(upload):
    """pdf 쪽수 (라이브러리 없이 /Type /Page 개수로 셈). 못 세면 None."""
    try:
        data = upload.read()
        upload.seek(0)
    except Exception:  # noqa: BLE001 — 쪽수는 없어도 돼요
        return None
    import re

    count = len(re.findall(rb'/Type\s*/Page(?!s)', data))
    return count or None


def save_plan_file(user, project, upload):
    """기획안 파일 저장 → 지금 쓰는 기획안. 저장 위치는 plans/<원정대>/<무작위>.확장자 (사용자 파일 이름은 경로에 안 씀)."""
    ext = check_plan_file(upload)
    project = project_for_edit(user, project)
    text = None
    if ext in TEXT_EXTENSIONS:
        text = upload.read().decode('utf-8', errors='replace')[:TEXT_LIMIT]
        upload.seek(0)
    pages = _pdf_pages(upload) if ext == '.pdf' else (1 if ext not in TEXT_EXTENSIONS else None)
    stored = default_storage.save(f'plans/{project.pk}/{uuid.uuid4().hex}{ext}', upload)
    try:
        return set_current_document(
            project, user, source_type=PlanDocument.FILE, file_name=os.path.basename(upload.name)[:255], file_size=upload.size,
            mime_type=PLAN_FILE_TYPES[ext], page_count=pages, storage_url=stored, text_content=text,
        )
    except Exception:
        default_storage.delete(stored)
        raise


def save_plan_text(user, project, text):
    """기획 문서 편집 (팀 변경 11/26: '기획문서 편집 가능'). 새 판으로 저장하고 이전 판은 기록으로 남겨요."""
    project = project_for_edit(user, project)
    text = text.strip()
    current = current_document(project)
    if current and current.source_type == PlanDocument.TEXT and (current.text_content or '') == text:
        return current  # 바뀐 게 없으면 새 판을 만들지 않아요
    return set_current_document(project, user, source_type=PlanDocument.TEXT, text_content=text[:TEXT_LIMIT])


def save_plan_link(user, project, url):
    project = project_for_edit(user, project)
    current = current_document(project)
    if current and current.source_type == PlanDocument.LINK and current.link_url == url:
        return current
    return set_current_document(project, user, source_type=PlanDocument.LINK, link_url=url)


def clear_document(user, project):
    """지금 기획안을 비워요 → '아직 기획 문서가 없어요' 상태 (기록은 남음)."""
    require_leader(user, project)
    PlanDocument.objects.filter(project=project, is_current=True).update(is_current=False)


def document_for_member(user, project, document_id):
    if membership(user, project) is None:
        raise Forbidden('원정대원만 볼 수 있어요')
    doc = project.plan_documents.filter(pk=document_id).first()
    if doc is None:
        raise NotFound('기획안을 찾을 수 없어요', code='plan_document_not_found')
    return doc


# ───────── 추천 루트 ─────────

@transaction.atomic
def recommend_route(user, project, *, deadline_at, unit, roles, source):
    """AI 추천 루트 → [{ id, name, source, reason }]. 저장은 안 해요 (프론트가 이어서 PUT /plan).

    source 의 기획안은 지금 기획안으로 기록해요 (파일은 이미 올린 fileId, 링크 · 글은 여기서).
    """
    project = project_for_edit(
        user, project, deadline_at=deadline_at, schedule_unit=unit,
        roles=[{'role_key': r.get('role'), 'label': r['label'], 'headcount': r.get('people', 1)} for r in roles],
    )
    kind = source['type']
    if kind == PlanDocument.FILE:
        document = current_document(project)
        if source.get('fileId'):
            document = project.plan_documents.filter(source_type=PlanDocument.FILE, pk=_pk(source['fileId']) or -1).first()
            if document is None:
                raise NotFound('기획안 파일을 찾을 수 없어요', code='plan_file_not_found')
    elif kind == PlanDocument.LINK:
        document = save_plan_link(user, project, source['url'])
    else:
        document = save_plan_text(user, project, source['text'])

    text = document.text_content if document else ''
    picks = recommend.recommend_checkpoints(text)
    return [{'id': f'r{i}', **pick} for i, pick in enumerate(picks, start=1)]


# ───────── 루트 진행 ─────────

def _require_climbing(project):
    if project.status != Project.CLIMBING:
        raise Conflict('아직 출발하지 않았어요. "이 루트로 출발하기"를 먼저 눌러 주세요', code='not_started')


@transaction.atomic
def start_route(user, project):
    """'이 루트로 출발하기' (리더): 출발 → 베이스 캠프 · 첫 구간에 도착 → 할 일 추천."""
    require_leader(user, project)
    project = Project.objects.select_for_update().get(pk=project.pk)
    if project.status != Project.PLANNING:
        raise Conflict('이미 출발했어요', code='already_started')
    if not screens(project).exists():
        raise Conflict('구간이 없어요. 루트를 먼저 만들어 주세요', code='no_checkpoints')
    now = timezone.now()
    project.status, project.started_at = Project.CLIMBING, now
    project.save(update_fields=['status', 'started_at', 'updated_at'])
    reschedule(project, start=now)
    arrive(ensure_base_camp(project))
    first = screens(project).first()
    arrive(first)
    if project.recommend_all_tasks:  # 설정 "전체 할 일 받기"
        for cp in screens(project).exclude(pk=first.pk):
            suggest_for(cp)
    return project


def arrive(checkpoint):
    """구간에 도착: 도착 시각을 남기고 할 일을 추천해요 (앞 구간의 막힌 요청도 반영)."""
    if checkpoint.arrived_at:
        return checkpoint
    checkpoint.arrived_at = timezone.now()
    checkpoint.save(update_fields=['arrived_at', 'updated_at'])
    suggest_for(checkpoint)
    return checkpoint


def suggest_for(checkpoint):
    """구간의 할 일 추천을 만들어 둬요. 이미 추천한 구간이면 그대로."""
    if checkpoint.tasks.exclude(origin=CheckpointTask.MANUAL).exists():
        return []
    from handoffs.models import HandoffCard

    blocked = HandoffCard.objects.filter(
        project=checkpoint.project, blocked_since__isnull=False, checkpoint__seq__lt=checkpoint.seq,
    ).exclude(status=HandoffCard.CONFIRMED) if checkpoint.seq > 0 else []
    picks = recommend.suggest_tasks(checkpoint, list(checkpoint.project.roles.all()), list(blocked))
    return CheckpointTask.objects.bulk_create([
        CheckpointTask(checkpoint=checkpoint, role=p['role'], title=p['title'][:255], reason=p['reason'],
                       origin=p['origin'], state=CheckpointTask.FIRST_STATE[p['origin']])
        for p in picks
    ])


@transaction.atomic
def complete_checkpoint(user, project, seq):
    """구간 완료 (리더): 그 화면이 디자인 · 프론트 · 백 모두 끝나 동작함 → 다음 구간에 도착."""
    require_leader(user, project)
    _require_climbing(project)
    cp = checkpoint_by_seq(project, seq)
    if cp is None:
        raise NotFound('구간을 찾을 수 없어요', code='checkpoint_not_found')
    if cp.completed_at:
        return cp
    cp.arrived_at = cp.arrived_at or timezone.now()
    cp.completed_at = timezone.now()
    cp.save(update_fields=['arrived_at', 'completed_at', 'updated_at'])
    nxt = screens(project).filter(seq__gt=cp.seq, completed_at__isnull=True).first()
    if nxt:
        arrive(nxt)
    return cp


@transaction.atomic
def reopen_checkpoint(user, project, seq):
    require_leader(user, project)
    cp = checkpoint_by_seq(project, seq)
    if cp is None:
        raise NotFound('구간을 찾을 수 없어요', code='checkpoint_not_found')
    cp.completed_at = None
    cp.save(update_fields=['completed_at', 'updated_at'])
    return cp


@transaction.atomic
def reach_summit(user, project):
    """정상 도착 (리더): 모든 화면 구간이 끝나야 해요."""
    require_leader(user, project)
    _require_climbing(project)
    left = screens(project).filter(completed_at__isnull=True)
    if left.exists():
        raise Conflict(f'아직 안 끝난 구간이 있어요 ({", ".join(c.name for c in left)})', code='checkpoints_left')
    project.status, project.completed_at = Project.COMPLETED, timezone.now()
    project.save(update_fields=['status', 'completed_at', 'updated_at'])
    return project


# ───────── 구간 할 일 ─────────

def _can_touch_role(user, project, role):
    if is_leader(user, project):
        return True
    m = membership(user, project)
    return m is not None and role in roles_of(m)


def add_task(user, project, seq, *, role, title, assignee=None):
    cp = checkpoint_by_seq(project, seq)
    if cp is None:
        raise NotFound('구간을 찾을 수 없어요', code='checkpoint_not_found')
    if not _can_touch_role(user, project, role):
        raise Forbidden('내 역할의 할 일만 더할 수 있어요', code='role_only')
    return CheckpointTask.objects.create(
        checkpoint=cp, role=role, title=title, origin=CheckpointTask.MANUAL, state=CheckpointTask.SELECTED, assignee_member=assignee,
    )


def task_for(user, project, task_id):
    task = CheckpointTask.objects.select_related('checkpoint', 'role').filter(pk=task_id, checkpoint__project=project).first()
    if task is None:
        raise NotFound('할 일을 찾을 수 없어요', code='task_not_found')
    if not _can_touch_role(user, project, task.role):
        raise Forbidden('내 역할의 할 일만 고칠 수 있어요', code='role_only')
    return task


def update_task(task, *, state=None, title=None, assignee=..., ):
    fields = []
    if title is not None and title != task.title:
        task.title = title
        fields.append('title')
    if state is not None and state != task.state:
        task.state = state
        task.done_at = timezone.now() if state == CheckpointTask.DONE else None
        fields += ['state', 'done_at']
    if assignee is not ...:
        task.assignee_member = assignee
        fields.append('assignee_member')
    if fields:
        task.save(update_fields=fields)
    return task


def next_seq(project):
    return (project.checkpoints.aggregate(m=Max('seq'))['m'] or 0) + 1
