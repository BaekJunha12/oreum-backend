from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from config.testing import ErdContractMixin

from .models import Workspace, WorkspaceMember
from .services import add_member, create_workspace, personal_workspace, workspaces_of

User = get_user_model()


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Workspace, set()), (WorkspaceMember, set())]


class ServiceTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user('me@example.com', name='나')
        self.other = User.objects.create_user('other@example.com', name='남')

    def test_creator_becomes_owner(self):
        ws = create_workspace(self.me, 'A11y Team')
        member = WorkspaceMember.objects.get(workspace=ws, user=self.me)
        self.assertEqual(member.permission_role, 'owner')
        self.assertEqual(ws.created_by, self.me)

    def test_only_my_workspaces_in_join_order(self):
        first = create_workspace(self.me, '첫째')
        create_workspace(self.other, '남의 것')
        second = create_workspace(self.other, '나중에 들어감')
        add_member(second, self.me)
        self.assertEqual(list(workspaces_of(self.me)), [first, second])

    def test_add_member_twice_keeps_one_row_and_role(self):
        ws = create_workspace(self.me, 'A11y Team')
        add_member(ws, self.me)  # 이미 주인
        self.assertEqual(WorkspaceMember.objects.filter(workspace=ws).count(), 1)
        self.assertEqual(WorkspaceMember.objects.get(workspace=ws, user=self.me).permission_role, 'owner')

    def test_personal_workspace_is_made_only_when_needed(self):
        ws = personal_workspace(self.me)
        self.assertEqual(ws.name, '나의 스페이스')
        self.assertEqual(personal_workspace(self.me), ws)

    def test_same_member_twice_is_rejected_by_db(self):
        ws = create_workspace(self.me, 'A11y Team')
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkspaceMember.objects.create(workspace=ws, user=self.me)

    def test_unknown_permission_role_is_rejected_by_db(self):
        ws = create_workspace(self.me, 'A11y Team')
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkspaceMember.objects.create(workspace=ws, user=self.other, permission_role='king')


class ApiTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user('me@example.com', name='나')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.create(user=self.me).key}')

    def test_list_in_front_end_shape(self):
        ws = create_workspace(self.me, 'A11y Team')
        res = self.client.get('/api/workspaces')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [{'id': str(ws.pk), 'name': 'A11y Team'}])

    def test_empty_list_for_new_user(self):
        self.assertEqual(self.client.get('/api/workspaces').json(), [])

    def test_create(self):
        res = self.client.post('/api/workspaces', {'name': '캠퍼스 앱 팀'}, format='json')
        self.assertEqual(res.status_code, 201)
        ws = Workspace.objects.get(pk=int(res.json()['id']))
        self.assertTrue(WorkspaceMember.objects.filter(workspace=ws, user=self.me, permission_role='owner').exists())

    def test_create_needs_a_name(self):
        res = self.client.post('/api/workspaces', {'name': ''}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.json()['message'].startswith('name: '))

    def test_needs_login(self):
        self.assertEqual(APIClient().get('/api/workspaces').status_code, 401)


class AdminTests(TestCase):
    def test_workspace_admin_opens_with_members(self):
        admin = User.objects.create_superuser('admin@example.com', 'pw-123456789', name='관리자')
        ws = create_workspace(admin, 'A11y Team')
        self.client.force_login(admin)
        res = self.client.get(f'/admin/workspaces/workspace/{ws.pk}/change/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '관리자(주인)')
