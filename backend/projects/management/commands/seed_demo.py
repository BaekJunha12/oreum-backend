"""python manage.py seed_demo — 프론트 예시 화면과 같은 사람 · 원정대를 DB 에 넣어요.

프론트를 서버에 붙였을 때 바로 로그인해 볼 수 있게 하는 개발용 명령이에요. 여러 번 실행해도 한 벌만 생겨요.
처음 만들 때 루트(구간 4개) · 예시 요청 카드 · 방 대화 · GitHub PR · 배포 기록(prod · dev)도 같이 넣어요.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project, ProjectRole
from projects.services import create_invitation, create_project, join_project
from workspaces.models import Workspace
from workspaces.services import create_workspace

PASSWORD = 'oreum-demo-1234'
# (이메일, 이름, 역할) — 프론트 main2/src/data 의 예시 사람들. 첫 사람이 리더예요.
PEOPLE = [
    ('hyeseung@example.com', '김혜승', 'design'),
    ('seoyeon@example.com', '박서연', 'design'),
    ('minjun@example.com', '이민준', 'front'),
    ('jiwoo@example.com', '최지우', 'front'),
    ('hayun@example.com', '정하윤', 'back'),
]
ROLES = [
    {'role_key': 'design', 'label': '디자인', 'headcount': 2},
    {'role_key': 'front', 'label': '프론트', 'headcount': 2},
    {'role_key': 'back', 'label': '백', 'headcount': 2},  # 한 자리는 비워 두고 초대 링크를 만들어 둬요
]
WORKSPACE, PROJECT = 'A11y Team', '캠퍼스 앱'
DEADLINE = datetime(2026, 12, 3, 18, 0, tzinfo=ZoneInfo('Asia/Seoul'))


class Command(BaseCommand):
    help = '프론트 예시와 같은 사용자 · 팀 스페이스 · 원정대를 만들어요 (개발용)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='DEBUG 가 꺼진 서버에서도 실행')

    @transaction.atomic
    def handle(self, *args, force=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError('개발용 명령이에요. 배포 서버에서 정말 실행하려면 --force 를 붙여 주세요.')

        User = get_user_model()
        users = []
        for email, name, _ in PEOPLE:
            user = User.objects.filter(email=email).first() or User.objects.create_user(email, PASSWORD, name=name)
            users.append(user)

        leader = users[0]
        project = Project.objects.filter(name=PROJECT, workspace__name=WORKSPACE).first()
        if project:
            self.stdout.write(self.style.WARNING(f'이미 있어요: {WORKSPACE} / {PROJECT} (그대로 둠)'))
        else:
            workspace = Workspace.objects.filter(name=WORKSPACE, memberships__user=leader).first() or create_workspace(leader, WORKSPACE)
            project = create_project(leader, name=PROJECT, deadline_at=DEADLINE, workspace=workspace, roles=ROLES, my_roles=[PEOPLE[0][2]])
            for user, (_, _, role_key) in zip(users[1:], PEOPLE[1:]):
                join_project(user, project, ProjectRole.objects.filter(project=project, role_key=role_key))
            back = ProjectRole.objects.get(project=project, role_key='back')
            invitation = create_invitation(leader, project, roles=[back])
            self.stdout.write(self.style.SUCCESS(f'만들었어요: {WORKSPACE} / {PROJECT} (마감 12/03 18:00)'))
            self.stdout.write(f'  백 자리 초대 토큰: {invitation.token}')
            seed_activity(project, users)
            self.stdout.write('  루트 · 요청 카드 · 방 대화 · PR · 배포 기록도 넣었어요')

        self.stdout.write('\n로그인 (비밀번호는 모두 ' + PASSWORD + ')')
        for email, name, role_key in PEOPLE:
            self.stdout.write(f'  {email:<24} {name}  {role_key}')


SCREENS = ['로그인', '메인 피드', '마이페이지', '알림']
MESSAGES = [  # (사람 번호, 방, 글)
    (0, 'all', '이번 주 목표는 로그인 · 메인 피드까지예요!'),
    (1, 'design', '메인 피드 카드 그림자 시안 올렸어요'),
    (2, 'front', '로그인 폼 PR 올렸어요, 리뷰 부탁해요'),
    (4, 'back', '로그인 API 배포 끝났어요'),
]


def seed_activity(project, users):
    """루트 · 카드 · 대화 · GitHub · 배포 기록 예시."""
    from django.utils import timezone

    from handoffs.services import reset_demo
    from plans.services import reschedule, sync_checkpoints
    from rooms.services import room_by_key, send_message
    from versions.models import AppVersion, GithubPullRequest, GithubRepository

    leader = users[0]
    sync_checkpoints(project, [{'name': n, 'source': 'plan'} for n in SCREENS])
    reschedule(project)
    reset_demo(leader, project)
    for who, room, text in MESSAGES:
        send_message(users[who], room_by_key(project, room), {'text': text})
    repo = GithubRepository.objects.create(project=project, owner='a11y-team', name='campus-app', connected_by=leader)
    now = timezone.now()
    pr = GithubPullRequest.objects.create(repo=repo, number=24, title='메인 화면 레이아웃', head_branch='feat/main-layout', base_branch='main',
                                          author_login='minjun', stage=GithubPullRequest.DEPLOYED, url='https://github.com/a11y-team/campus-app/pull/24',
                                          merged_at=now, deployed_at=now)
    GithubPullRequest.objects.create(repo=repo, number=27, title='로그인 폼', head_branch='feat/login-form', base_branch='main',
                                     author_login='jiwoo', stage=GithubPullRequest.REVIEW, url='https://github.com/a11y-team/campus-app/pull/27')
    AppVersion.objects.create(project=project, environment=AppVersion.PROD, version_label='v1.2.0', branch='main',
                              site_url='https://campus.example.com', source_pr=pr, deployed_at=now)
    AppVersion.objects.create(project=project, environment=AppVersion.DEV, version_label='v1.3.0-dev', branch='dev',
                              site_url='https://dev.campus.example.com', deployed_at=now)
