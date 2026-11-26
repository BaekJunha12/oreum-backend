"""기획안 · 루트 규칙. 다른 앱(카드 · 방)도 구간 표를 직접 뒤지지 말고 이 함수들을 불러요.

자주 쓸 것
    current_checkpoint(project)        지금 구간 (새 카드 · 새 메시지의 기본 구간). 항상 구간 하나를 돌려줘요
    checkpoint_by_seq(project, seq)    프론트의 구간 번호(0 = 베이스 캠프)로 구간 찾기. 없으면 None

기획안 API 가 쓰는 것
    project_for_edit(user)             일정 · 기획안을 고칠 원정대 (리더만, 원정대가 없으면 새로 만듦)
    set_current_document(project, user, **칸)   지금 쓰는 기획안을 바꿈 (이전 것은 is_current=False)
    save_plan_file(user, upload)       올린 기획안 파일 검사 · 저장 → PlanDocument
    recommend_route(user, ...)         AI 추천 루트 → [{ id, name }] (지금은 고정 목록, 저장은 안 함)
"""
import os
import uuid
from datetime import datetime, timedelta

from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from projects.errors import Forbidden, NotFound
from projects.models import Project
from projects.services import create_project, current_project, is_leader

from .models import BASE_CAMP_NAME, MAX_CHECKPOINTS, Checkpoint, PlanDocument

DEFAULT_PROJECT_NAME = '내 원정대'
MAX_PLAN_FILE_BYTES = 20 * 1024 * 1024  # 20MB
# 올릴 수 있는 기획안 파일 (프론트 StartPage 의 accept=".pdf,.md,.txt,image/*"). 확장자 → 저장해 둘 MIME
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
TEXT_LIMIT = 200_000  # 본문으로 저장할 글자 수 (AI 에 넣을 때는 더 줄일 수 있어요)
DEMO_ROUTE = ['로그인', '메인 피드', '마이페이지', '알림']  # AI 가 붙기 전의 추천 루트 (프론트 목업과 같아요)


def checkpoint_by_seq(project, seq):
    """프론트의 카드 · 메시지는 구간을 id 가 아니라 번호(seq)로 가리켜요. 그 번호의 구간 (없으면 None)."""
    return project.checkpoints.filter(seq=seq).first()


def current_checkpoint(project):
    """지금 구간. 새 카드 · 새 메시지에 구간을 따로 안 골랐을 때 붙는 구간이에요.

    아직 끝나지 않은 화면 구간(seq 1~) 중 번호가 가장 작은 것. 규칙 순서:
      1. 안 끝난 화면 구간이 있으면 그중 첫 번째 (구간끼리 겹쳐 진행돼도 앞 번호가 먼저)
      2. 화면 구간이 전부 끝났으면 마지막 화면 구간
      3. 화면 구간이 하나도 없으면 베이스 캠프 (seq 0)

    원정대가 "출발했는지"(projects.status)는 안 봐요. 프론트에는 아직 출발 호출이 없어서 status 가 늘 planning 이고,
    프론트의 기본값도 1번 구간이에요. 구간에 "도착"하는 것(arrived_at)도 지금 구간을 바꾸지 않아요 — 끝내야(completed_at) 넘어가요.
    """
    screens = project.checkpoints.filter(seq__gte=1)  # Checkpoint 는 seq 순서로 정렬돼 있어요
    return (
        screens.filter(completed_at__isnull=True).first()
        or screens.last()
        # 베이스 캠프는 원정대가 생길 때 만들어지지만(plans.signals), 지워졌어도 "항상 하나"는 지켜요
        or Checkpoint.objects.get_or_create(project=project, seq=0, defaults={'name': BASE_CAMP_NAME})[0]
    )


# ───────── 기획안 ─────────

def project_for_edit(user, **create):
    """일정 · 기획안을 고칠 원정대. 리더만 고칠 수 있어요 (초대와 같은 규칙).

    프론트는 시작하기에서 원정대가 아직 없어도 바로 기획안을 올려요. 그래서 원정대가 하나도 없으면
    create 로 받은 값(+ 기본값)으로 새로 만들고, 만든 사람이 리더가 돼요.
    """
    project = current_project(user)
    if project is None:
        create.setdefault('name', DEFAULT_PROJECT_NAME)
        # ponytail: 마감을 모르는 채 만들 땐 임시값(오늘 + 7일 18:00). 곧바로 오는 PUT /plan 이 진짜 마감으로 덮어써요.
        # ponytail: 새 사용자가 요청 두 개를 동시에 보내면 원정대가 둘 생길 수 있어요 (프론트는 하나씩 보냄). 필요하면 사용자 행을 잠가요.
        create.setdefault('deadline_at', (timezone.localtime() + timedelta(days=7)).replace(hour=18, minute=0, second=0, microsecond=0))
        return create_project(user, **create)
    if not is_leader(user, project):
        raise Forbidden('리더만 할 수 있어요', code='leader_only')
    return project


@transaction.atomic
def set_current_document(project, user, **fields):
    """지금 쓰는 기획안을 바꿔요. 이전 기획안은 남겨 두고 is_current 만 끄고, 새 것을 현재로 만들어요."""
    Project.objects.select_for_update().get(pk=project.pk)  # 같은 원정대에 동시에 올려도 현재 기획안은 하나만
    PlanDocument.objects.filter(project=project, is_current=True).update(is_current=False)
    return PlanDocument.objects.create(project=project, uploaded_by=user, is_current=True, **fields)


def check_plan_file(upload):
    """올린 파일이 괜찮은지 보고 확장자(소문자)를 돌려줘요. 원정대를 만들기 전에 불러서, 잘못된 파일로는 아무것도 안 만들어져요."""
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in PLAN_FILE_TYPES:
        raise ValidationError('지원하지 않는 파일이에요. pdf · md · txt · 이미지(png, jpg, gif, webp)만 올릴 수 있어요')
    if upload.size == 0:
        raise ValidationError('빈 파일이에요')
    if upload.size > MAX_PLAN_FILE_BYTES:
        raise ValidationError(f'파일이 너무 커요 (최대 {MAX_PLAN_FILE_BYTES // 1024 // 1024}MB)')
    return ext


def save_plan_file(user, upload):
    """기획안 파일을 저장하고 지금 쓰는 기획안으로 해요.

    저장 위치는 plans/<원정대 id>/<무작위 이름><확장자> — 사용자가 정한 파일 이름은 경로에 안 쓰고 file_name 에만 남겨요.
    파일은 공개 주소로 열어 주지 않아요 (서버가 읽어서 AI 에 넘길 때만 써요).
    ponytail: 확장자와 크기만 봐요 (파일 내용이 진짜 pdf 인지는 안 봄). 쪽수(page_count)는 모름 → 비움, 필요해지면 pdf 라이브러리.
    """
    ext = check_plan_file(upload)
    project = project_for_edit(user)

    text = None
    if ext in TEXT_EXTENSIONS:
        text = upload.read().decode('utf-8', errors='replace')[:TEXT_LIMIT]
        upload.seek(0)

    stored = default_storage.save(f'plans/{project.pk}/{uuid.uuid4().hex}{ext}', upload)
    try:
        return set_current_document(
            project, user, source_type=PlanDocument.FILE, file_name=upload.name, file_size=upload.size,
            mime_type=PLAN_FILE_TYPES[ext], storage_url=stored, text_content=text,
        )
    except Exception:
        default_storage.delete(stored)  # 기록을 못 남겼으면 파일도 남기지 않아요
        raise


# ───────── AI 추천 루트 ─────────

def recommend_checkpoint_names(*, document, deadline, roles):
    """기획안으로 만든 체크포인트 이름들 (베이스 캠프 · 정상 빼고). 지금은 AI 없이 고정 목록이에요.

    document = 기획안 PlanDocument (프론트가 예시 파일 이름만 보낸 경우 None), deadline · roles = 요청 값. 지금은 아무것도 안 써요.
    AI 를 붙일 때는 **이 함수 본문만** 바꾸면 돼요. 같이 할 것:
      - `claude-api` 스킬로 모델 · PDF 입력 방식 확인, 키는 환경 변수(ANTHROPIC_API_KEY), 프론트가 60초까지 기다려서 50초쯤에 끊고 504 { message, code }
      - 같은 기획안이면 AI 를 다시 부르지 않기: 프론트 sourceSignature(planStore.ts)를 파이썬으로 옮기고(UTF-16 djb2, node 로 값 대조)
        **AI 가 처음 만든 결과**를 signature 로 캐시 — 고쳐 둔 루트를 돌려주면 "추천으로 되돌리기"가 아무 일도 안 해요
      - 링크는 서버가 가져오지 않아요 (SSRF · 로그인이 필요한 문서). 읽을 수 없다는 안내 오류로
    """
    return list(DEMO_ROUTE)


@transaction.atomic
def recommend_route(user, *, deadline, roles, source):
    """AI 추천 루트 만들기. 체크포인트를 저장하지는 않아요 (프론트가 이어서 PUT /plan 으로 저장).

    기획안은 원정대의 지금 기획안으로 기록해요: 파일은 이미 올려 둔 것(fileId)을 가리키고, 링크 · 글은 여기서 기록해요
    (같은 링크 · 글로 다시 부르면 — "추천으로 되돌리기" — 새로 만들지 않아요). 리더만, 원정대가 없으면 요청의 마감 · 역할로 만들어요.
    """
    project = project_for_edit(
        user,
        deadline_at=timezone.make_aware(datetime.combine(deadline['date'], deadline['time'])),
        schedule_unit=deadline['unit'],
        roles=[{'role_key': r.get('role'), 'label': r['label'], 'headcount': r['people']} for r in roles],
    )  # 아래에서 오류가 나면 방금 만든 원정대도 같이 되돌려져요 (atomic)

    kind = source['type']
    if kind == PlanDocument.FILE:
        document = None  # fileId 없이 이름만 오면 (예시 기획안) 가리킬 기록이 없어요
        if source.get('fileId'):
            document = PlanDocument.objects.filter(project=project, source_type=PlanDocument.FILE, pk=_pk(source['fileId'])).first()
            if document is None:
                raise NotFound('기획안 파일을 찾을 수 없어요', code='plan_file_not_found')
    else:
        fields = {'source_type': kind, 'link_url': source['url']} if kind == PlanDocument.LINK else {'source_type': kind, 'text_content': source['text'][:TEXT_LIMIT]}
        document = PlanDocument.objects.filter(project=project, is_current=True, **fields).first() or set_current_document(project, user, **fields)

    names = recommend_checkpoint_names(document=document, deadline=deadline, roles=roles)
    return [{'id': f'r{i}', 'name': name} for i, name in enumerate(names[:MAX_CHECKPOINTS], start=1)]


def _pk(value):
    """프론트가 보낸 글자 id → 숫자 (숫자가 아니면 어떤 행도 가리키지 않는 -1)."""
    return int(value) if value.isascii() and value.isdigit() else -1
