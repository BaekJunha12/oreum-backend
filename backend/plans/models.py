"""B. 기획안 · 루트 (docs/db/erd.sql).

지금은 checkpoints 만 있어요. plan_documents, checkpoint_tasks 는 B-02 에서 더해요.
원정대 · 역할 표는 projects 앱 것이라 여기서는 가리키기만 해요 (고칠 때는 projects.services).
"""
from django.db import models

from projects.models import Project

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
