"""B. 기획안 · 루트 — plan_documents, checkpoints, checkpoint_tasks (docs/db/erd.sql v0.5).

원정대 · 역할 · 원정대원 표는 projects 앱 것이라 여기서는 가리키기만 해요.
"""
from django.conf import settings
from django.db import models

from projects.models import Project, ProjectMember, ProjectRole

# 화면 구간은 최대 8개 (베이스 캠프 제외, 팀 확정 11/25). ERD 에 "앱에서 검사" 라고 적혀 있어 서비스에서 지켜요.
MAX_CHECKPOINTS = 8
BASE_CAMP_NAME = '베이스 캠프'


class PlanDocument(models.Model):
    """기획안. 파일(file) · 링크(link) · 직접 입력(text). 지금 쓰는 기획안은 원정대마다 하나(is_current).

    고치면 행을 덮어쓰지 않고 새 행을 만들어요 → 이전 판은 is_current=False 로 남아 기록(버전)이 돼요.
    """

    FILE, LINK, TEXT = 'file', 'link', 'text'
    SOURCE_TYPES = [(FILE, '파일'), (LINK, '링크'), (TEXT, '직접 입력')]

    id = models.BigAutoField(primary_key=True, db_column='plan_document_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='plan_documents')
    source_type = models.CharField('넣은 방법', max_length=10, choices=SOURCE_TYPES)
    file_name = models.CharField('파일 이름', max_length=255, null=True, blank=True)
    file_size = models.BigIntegerField('파일 크기(바이트)', null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    page_count = models.IntegerField('쪽수', null=True, blank=True)
    storage_url = models.CharField('올린 파일 저장 위치', max_length=700, null=True, blank=True)
    link_url = models.CharField('링크 주소', max_length=700, null=True, blank=True)
    text_content = models.TextField('본문 (직접 입력 · 파일에서 뽑은 글자)', null=True, blank=True)
    is_current = models.BooleanField('지금 쓰는 기획안', default=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='uploaded_by', related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'plan_documents'
        verbose_name = verbose_name_plural = '기획안'
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(source_type__in=['file', 'link', 'text']), name='CK_plan_document_source_type'),
            # 지금 쓰는 기획안은 원정대마다 하나 (ERD 에 없는 규칙 — docs/db/README.md)
            models.UniqueConstraint(fields=['project'], condition=models.Q(is_current=True), name='UQ_plan_document_current'),
        ]

    def __str__(self):
        return self.file_name or self.link_url or f'{self.get_source_type_display()} 기획안'


class Checkpoint(models.Model):
    """루트의 구간. seq 0 = 베이스 캠프(항상 하나), 1~ = 화면 구간. 정상은 projects.deadline_at.

    v0.5: 시간 단위 일정("n시간 남음")을 위해 시작 · 목표를 DATE → DATETIME(start_at · end_at) 으로 바꿨어요.
    프론트의 카드 · 메시지는 구간을 id 가 아니라 번호(seq)로 가리켜요.
    """

    PLAN, AI, MANUAL = 'plan', 'ai', 'manual'
    SOURCES = [(PLAN, '기획안'), (AI, 'AI 추천'), (MANUAL, '직접 추가')]

    id = models.BigAutoField(primary_key=True, db_column='checkpoint_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='checkpoints')
    seq = models.IntegerField('순서 (0 = 베이스 캠프)')
    name = models.CharField('구간 이름', max_length=100)
    start_at = models.DateTimeField('구간 시작', null=True, blank=True)
    end_at = models.DateTimeField('목표 완성', null=True, blank=True)
    source = models.CharField('만든 방법', max_length=10, choices=SOURCES, default=PLAN)
    order_reason = models.CharField('기획안 순서와 다르게 놓은 이유', max_length=500, null=True, blank=True)
    arrived_at = models.DateTimeField('도착 시각', null=True, blank=True)
    completed_at = models.DateTimeField('구간 완료 시각', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'checkpoints'
        verbose_name = verbose_name_plural = '구간'
        ordering = ['seq']
        constraints = [
            models.UniqueConstraint(fields=['project', 'seq'], name='UQ_checkpoint_seq'),
            models.CheckConstraint(condition=models.Q(source__in=['plan', 'ai', 'manual']), name='CK_checkpoint_source'),
        ]

    def __str__(self):
        return f'{self.seq} · {self.name}'

    @property
    def is_base_camp(self):
        return self.seq == 0


class CheckpointTask(models.Model):
    """구간의 세부 할 일 (2 depth). 역할(파트)별. 덜 끝난 할 일도 원래 구간에 남아요.

    처음 state: plan → selected(기본으로 담김), ai → suggested(직접 골라야 담김), manual → selected.
    """

    PLAN, AI, MANUAL = 'plan', 'ai', 'manual'
    ORIGINS = [(PLAN, '기획안'), (AI, 'AI 추천'), (MANUAL, '직접 추가')]
    SUGGESTED, SELECTED, DONE, DISMISSED = 'suggested', 'selected', 'done', 'dismissed'
    STATES = [(SUGGESTED, '제안'), (SELECTED, '담음'), (DONE, '끝남'), (DISMISSED, '안 고름')]
    FIRST_STATE = {PLAN: SELECTED, AI: SUGGESTED, MANUAL: SELECTED}

    id = models.BigAutoField(primary_key=True, db_column='task_id')
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.CASCADE, related_name='tasks')
    # ERD 에 ON DELETE 없음 = RESTRICT: 할 일이 있는 역할만 따로 지우는 건 막아요 (원정대째 지울 때는 같이 지워짐)
    role = models.ForeignKey(ProjectRole, on_delete=models.RESTRICT, related_name='+')
    assignee_member = models.ForeignKey(ProjectMember, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    title = models.CharField('할 일', max_length=255)
    reason = models.CharField('AI 추천 이유', max_length=500, null=True, blank=True)
    origin = models.CharField('출처', max_length=10, choices=ORIGINS)
    state = models.CharField('상태', max_length=10, choices=STATES)
    done_at = models.DateTimeField('끝낸 시각', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'checkpoint_tasks'
        verbose_name = verbose_name_plural = '구간 할 일'
        ordering = ['checkpoint__seq', 'id']
        constraints = [
            models.CheckConstraint(condition=models.Q(origin__in=['plan', 'ai', 'manual']), name='CK_checkpoint_task_origin'),
            models.CheckConstraint(condition=models.Q(state__in=['suggested', 'selected', 'done', 'dismissed']), name='CK_checkpoint_task_state'),
        ]

    def __str__(self):
        return self.title
