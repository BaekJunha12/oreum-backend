"""B. 기획안 · 루트 (docs/db/erd.sql).

checkpoints, plan_documents, checkpoint_tasks
원정대 · 역할 · 원정대원 표는 projects 앱 것이라 여기서는 가리키기만 해요 (고칠 때는 projects.services).
"""
from django.conf import settings
from django.db import models

from projects.models import Project, ProjectMember, ProjectRole

# 화면 구간은 최대 8개예요 (베이스 캠프 제외, 팀 확정 11/25). ERD 에도 "앱에서 검사" 라고 적혀 있어서 표 제약이 아니라 서비스에서 지켜요.
MAX_CHECKPOINTS = 8
BASE_CAMP_NAME = '베이스 캠프'


class Checkpoint(models.Model):
    """루트의 구간(체크포인트).

    seq 가 구간의 정체성이에요. 0 = 베이스 캠프(원정대마다 항상 하나, 공통 작업), 1~ = 화면 구간(순서대로).
    프론트의 카드 · 메시지는 구간을 id 가 아니라 이 번호로 가리켜요 (HandoffCard.checkpoint).
    정상(마지막)은 구간이 아니라 projects.deadline_at 이에요.
    """

    PLAN, AI, MANUAL = 'plan', 'ai', 'manual'
    SOURCES = [(PLAN, '기획안'), (AI, 'AI 추천'), (MANUAL, '직접 추가')]

    id = models.BigAutoField(primary_key=True, db_column='checkpoint_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='checkpoints')
    seq = models.IntegerField('순서 (0 = 베이스 캠프)')
    name = models.CharField('구간 이름', max_length=100)
    start_date = models.DateField('구간 시작일', null=True, blank=True)
    end_date = models.DateField('목표 완성일', null=True, blank=True)
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


class PlanDocument(models.Model):
    """기획안. 파일을 올리거나(file), 링크를 넣거나(link), 직접 적은(text) 것. 지금 쓰는 기획안은 원정대마다 하나(is_current)예요."""

    FILE, LINK, TEXT = 'file', 'link', 'text'
    SOURCE_TYPES = [(FILE, '파일'), (LINK, '링크'), (TEXT, '직접 입력')]

    id = models.BigAutoField(primary_key=True, db_column='plan_document_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='plan_documents')
    source_type = models.CharField('넣은 방법', max_length=10, choices=SOURCE_TYPES)
    file_name = models.CharField('파일 이름', max_length=255, null=True, blank=True)
    file_size = models.BigIntegerField('파일 크기(바이트)', null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    page_count = models.IntegerField('쪽수 (모르면 비움)', null=True, blank=True)
    storage_url = models.CharField('올린 파일 저장 위치', max_length=700, null=True, blank=True)
    link_url = models.CharField('링크 주소', max_length=700, null=True, blank=True)
    text_content = models.TextField('직접 입력한 본문 · 파일에서 뽑은 글자', null=True, blank=True)
    is_current = models.BooleanField('지금 쓰는 기획안', default=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='uploaded_by', related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'plan_documents'
        verbose_name = verbose_name_plural = '기획안'
        constraints = [
            models.CheckConstraint(condition=models.Q(source_type__in=['file', 'link', 'text']), name='CK_plan_document_source_type'),
        ]

    def __str__(self):
        return self.file_name or self.link_url or f'{self.get_source_type_display()} 기획안'


class CheckpointTask(models.Model):
    """구간의 세부 할 일 (2 depth). 역할(파트)별이고, 덜 끝난 할 일도 원래 구간에 그대로 남아요.

    origin = 어디서 왔는지, state = 지금 상태. 처음 값은 plan → selected(기본으로 담김), ai → suggested(직접 골라야 담김)이고
    DB 기본값이 아니라 할 일을 만드는 서비스에서 정해요.
    """

    PLAN, AI, MANUAL = 'plan', 'ai', 'manual'
    ORIGINS = [(PLAN, '기획안'), (AI, 'AI 추천'), (MANUAL, '직접 추가')]
    SUGGESTED, SELECTED, DONE, DISMISSED = 'suggested', 'selected', 'done', 'dismissed'
    STATES = [(SUGGESTED, '제안'), (SELECTED, '담음'), (DONE, '끝남'), (DISMISSED, '안 고름')]

    id = models.BigAutoField(primary_key=True, db_column='task_id')
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.CASCADE, related_name='tasks')
    # 사람보다 역할 자리에 먼저 배정해요. ERD 에 ON DELETE 가 없다 = MySQL 기본(RESTRICT):
    # 할 일이 있는 역할만 따로 지우는 건 막고, 원정대 전체를 지울 때는 할 일도 구간과 같이 지워져서 막지 않아요 (PROTECT 는 이것도 막음)
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
        constraints = [
            models.CheckConstraint(condition=models.Q(origin__in=['plan', 'ai', 'manual']), name='CK_checkpoint_task_origin'),
            models.CheckConstraint(condition=models.Q(state__in=['suggested', 'selected', 'done', 'dismissed']), name='CK_checkpoint_task_state'),
        ]

    def __str__(self):
        return self.title
