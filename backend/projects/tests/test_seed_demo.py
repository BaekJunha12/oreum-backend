from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from projects.models import Project, ProjectInvitation, ProjectMember
from projects.services import current_project


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    def run_seed(self):
        out = StringIO()
        call_command('seed_demo', stdout=out)
        return out.getvalue()

    def test_creates_the_front_end_example_team_once(self):
        first = self.run_seed()
        second = self.run_seed()
        self.assertIn('만들었어요', first)
        self.assertIn('이미 있어요', second)
        project = Project.objects.get()
        self.assertEqual(ProjectMember.objects.filter(project=project).count(), 5)
        self.assertEqual(ProjectInvitation.objects.filter(project=project, status='pending').count(), 1)
        self.assertEqual(project.deadline_at.isoformat(), '2026-12-03T09:00:00+00:00')
        # 루트 · 카드 · 대화 · GitHub · 배포 기록 예시도 한 벌
        self.assertEqual(list(project.checkpoints.filter(seq__gt=0).values_list('name', flat=True)), ['로그인', '메인 피드', '마이페이지', '알림'])
        self.assertTrue(project.cards.exists())
        self.assertEqual(project.rooms.get(role__isnull=True).messages.count(), 1)
        self.assertEqual(project.versions.count(), 2)

    def test_demo_user_can_log_in_and_sees_role_and_workspace(self):
        self.run_seed()
        client = APIClient()
        res = client.post('/api/auth/login', {'email': 'minjun@example.com', 'password': 'oreum-demo-1234'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['user']['role'], 'front')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['token']}")
        self.assertEqual([w['name'] for w in client.get('/api/workspaces').json()], ['A11y Team'])
        self.assertEqual(current_project(ProjectMember.objects.get(user__email='minjun@example.com').user).name, '캠퍼스 앱')

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=StringIO())
