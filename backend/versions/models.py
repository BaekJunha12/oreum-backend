"""F. GitHub 연결 · 버전 비교 — github_repositories, github_pull_requests, app_versions, compare_comments (docs/db/erd.sql).

팀 변경 11/26: "버전 비교 · 진행 상태" 탭이 생겼어요.
    - PR 은 작업 → 리뷰 → 병합 → 배포 네 단계로 보여요. 배포가 되면 PR 에 연결한 요청 카드가 자동으로 '전달됨'이 돼요 (is_auto).
    - 배포 기록(app_versions) 두 개를 골라 화면을 나란히 보고, 그 위에 코멘트(핀)를 남겨요.
    - 코멘트는 "요청보내기"로 바로 요청 카드를 만들 수 있어요 (card).
"""
from django.conf import settings
from django.db import models

from handoffs.models import HandoffCard
from projects.models import Project, ProjectRole


class GithubRepository(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='repo_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='repositories')
    owner = models.CharField('GitHub 소유자', max_length=100)
    name = models.CharField('저장소 이름', max_length=100)
    installation_id = models.CharField('GitHub App 설치 ID', max_length=50, null=True, blank=True)
    connected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='connected_by', related_name='+')
    connected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'github_repositories'
        verbose_name = verbose_name_plural = 'GitHub 연결'
        ordering = ['connected_at', 'id']
        constraints = [models.UniqueConstraint(fields=['project', 'owner', 'name'], name='UQ_project_repo')]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f'{self.owner}/{self.name}'


class GithubPullRequest(models.Model):
    WORK, REVIEW, MERGED, DEPLOYED = 'work', 'review', 'merged', 'deployed'
    STAGES = [(WORK, '작업'), (REVIEW, '리뷰'), (MERGED, '병합'), (DEPLOYED, '배포')]
    ORDER = [WORK, REVIEW, MERGED, DEPLOYED]

    id = models.BigAutoField(primary_key=True, db_column='pr_id')
    repo = models.ForeignKey(GithubRepository, on_delete=models.CASCADE, related_name='pulls')
    number = models.IntegerField('PR 번호')
    title = models.CharField(max_length=255)
    head_branch = models.CharField('작업 브랜치', max_length=255)
    base_branch = models.CharField('합칠 브랜치', max_length=255)
    author_login = models.CharField('작성자 GitHub 아이디', max_length=100, null=True, blank=True)
    stage = models.CharField(max_length=10, choices=STAGES, default=WORK)
    url = models.CharField(max_length=500)
    merged_at = models.DateTimeField(null=True, blank=True)
    deployed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'github_pull_requests'
        verbose_name = verbose_name_plural = 'PR 진행 단계'
        ordering = ['-updated_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['repo', 'number'], name='UQ_repo_pr_number'),
            models.CheckConstraint(condition=models.Q(stage__in=['work', 'review', 'merged', 'deployed']), name='CK_pr_stage'),
        ]

    def __str__(self):
        return f'#{self.number} {self.title}'


class AppVersion(models.Model):
    PROD, DEV = 'prod', 'dev'
    ENVIRONMENTS = [(PROD, '지금 서비스 중'), (DEV, '개발 서버')]

    id = models.BigAutoField(primary_key=True, db_column='app_version_id')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='versions')
    environment = models.CharField(max_length=10, choices=ENVIRONMENTS)
    version_label = models.CharField('버전', max_length=50)
    branch = models.CharField(max_length=100, null=True, blank=True)
    site_url = models.CharField('화면을 불러올 주소', max_length=700)
    source_pr = models.ForeignKey(GithubPullRequest, on_delete=models.SET_NULL, null=True, blank=True, db_column='source_pr_id', related_name='versions')
    deployed_at = models.DateTimeField('배포 시각')

    class Meta:
        db_table = 'app_versions'
        verbose_name = verbose_name_plural = '배포 기록'
        ordering = ['-deployed_at', '-id']
        constraints = [models.CheckConstraint(condition=models.Q(environment__in=['prod', 'dev']), name='CK_version_environment')]

    def __str__(self):
        return f'{self.environment} {self.version_label}'


class CompareComment(models.Model):
    COMMENT, MEMO = 'comment', 'memo'
    KINDS = [(COMMENT, '코멘트'), (MEMO, '메모')]

    id = models.BigAutoField(primary_key=True, db_column='comment_id')
    app_version = models.ForeignKey(AppVersion, on_delete=models.CASCADE, related_name='comments')
    screen_name = models.CharField('화면', max_length=100)
    pin_x = models.IntegerField(null=True, blank=True)
    pin_y = models.IntegerField(null=True, blank=True)
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='author_user_id', related_name='+')
    author_role = models.ForeignKey(ProjectRole, on_delete=models.SET_NULL, null=True, blank=True, db_column='author_role_id', related_name='+')
    kind = models.CharField(max_length=10, choices=KINDS, default=COMMENT)
    body = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, db_column='parent_comment_id', related_name='replies')
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, db_column='resolved_by', related_name='+')
    resolved_at = models.DateTimeField(null=True, blank=True)
    card = models.ForeignKey(HandoffCard, on_delete=models.SET_NULL, null=True, blank=True, related_name='compare_comments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compare_comments'
        verbose_name = verbose_name_plural = '버전 비교 코멘트'
        ordering = ['created_at', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(kind__in=['comment', 'memo']), name='CK_compare_comment_kind')]

    def __str__(self):
        return self.body[:40]
