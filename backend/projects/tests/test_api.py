from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from projects.models import Project, ProjectInvitation
from projects.testing import add_to, api_as, make_project, make_user
from workspaces.services import create_workspace


class MeRoleTests(TestCase):
    """로그인 응답의 user.role 이 지금 원정대의 역할을 따라가요."""

    def test_role_follows_current_project(self):
        project, leader = make_project(leader_role='back')
        res = api_as(leader).get('/api/auth/me')
        self.assertEqual(res.json()['role'], 'back')

    def test_login_response_has_the_role_too(self):
        project, _ = make_project()
        member = add_to(project, 'front@example.com', 'front')
        res = APIClient().post('/api/auth/login', {'email': 'front@example.com', 'password': 'climb-the-oreum-2026'}, format='json')
        self.assertEqual(res.json()['user']['role'], 'front')
        self.assertEqual(res.json()['user']['id'], str(member.user_id))

    def test_no_project_falls_back(self):
        user = make_user('alone@example.com')
        self.assertEqual(api_as(user).get('/api/auth/me').json()['role'], 'design')


class ProjectApiTests(TestCase):
    def setUp(self):
        self.leader = make_user('leader@example.com', '리더')
        self.client = api_as(self.leader)

    def create(self, **body):
        data = {'name': '캠퍼스 앱', 'deadlineAt': '2026-12-03T18:00:00+09:00', **body}
        return self.client.post('/api/projects', data, format='json')

    def test_create_with_front_end_role_shape(self):
        res = self.create(roles=[{'label': '디자인', 'people': 2, 'role': 'design'}, {'label': '기획', 'people': 1}], myRoles=['design'])
        self.assertEqual(res.status_code, 201, res.json())
        body = res.json()
        self.assertEqual(body['deadlineAt'], '2026-12-03T18:00:00+09:00')
        self.assertEqual([(r['label'], r['people'], r.get('role')) for r in body['roles']], [('디자인', 2, 'design'), ('기획', 1, None)])
        self.assertTrue(body['isLeader'])
        self.assertEqual(body['members'][0]['roles'][0]['role'], 'design')
        self.assertEqual(body['invitations'], [])

    def test_naive_deadline_is_korean_time(self):
        res = self.create(deadlineAt='2026-12-03 18:00')
        self.assertEqual(res.json()['deadlineAt'], '2026-12-03T18:00:00+09:00')

    def test_default_roles_when_none_given(self):
        res = self.create()
        self.assertEqual([r['role'] for r in res.json()['roles']], ['design', 'front', 'back'])

    def test_duplicate_role_labels_are_rejected(self):
        res = self.create(roles=[{'label': '디자인'}, {'label': '디자인'}])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['message'], 'roles: 역할 이름이 겹쳐요')

    def test_people_range_matches_front_end(self):
        res = self.create(roles=[{'label': '디자인', 'people': 21}])
        self.assertEqual(res.status_code, 400)

    def test_create_in_a_workspace_i_am_not_in(self):
        ws = create_workspace(make_user('owner@example.com'), '남의 팀')
        res = self.create(workspaceId=ws.pk)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()['message'], '이 팀 스페이스의 멤버가 아니에요')

    def test_list_marks_the_current_project(self):
        self.create(name='예전')
        self.create(name='지금')
        rows = self.client.get('/api/projects').json()
        self.assertEqual([(r['name'], r['current']) for r in rows], [('지금', True), ('예전', False)])

    def test_detail_is_members_only(self):
        project, _ = make_project(leader=make_user('l2@example.com'), name='남의 원정대')
        res = self.client.get(f'/api/projects/{project.pk}')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['message'], '원정대를 찾을 수 없어요')

    def test_members_see_no_invitations(self):
        project, leader = make_project(leader=self.leader)
        member = add_to(project, 'front@example.com', 'front')
        body = api_as(member.user).get(f'/api/projects/{project.pk}').json()
        self.assertNotIn('invitations', body)
        self.assertEqual([m['name'] for m in body['members']], ['리더', 'front'])


class InvitationApiTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()
        self.front = self.project.roles.get(role_key='front')
        self.client = api_as(self.leader)

    def invite(self, **body):
        return self.client.post(f'/api/projects/{self.project.pk}/invitations', body, format='json')

    def test_link_invitation_full_flow(self):
        res = self.invite(roleIds=[self.front.pk])
        self.assertEqual(res.status_code, 201, res.json())
        token = res.json()['token']
        self.assertEqual(res.json()['roles'], [{'id': str(self.front.pk), 'label': '프론트', 'people': 1, 'role': 'front'}])

        preview = APIClient().get(f'/api/invitations/{token}')  # 로그인 전
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()['project']['name'], '캠퍼스 앱')
        self.assertEqual(preview.json()['invitedBy'], {'name': '리더'})
        self.assertNotIn('token', preview.json())

        joiner = make_user('joiner@example.com', '새 대원')
        res = api_as(joiner).post(f'/api/invitations/{token}/accept')
        self.assertEqual(res.status_code, 200, res.json())
        self.assertEqual(res.json()['project']['id'], str(self.project.pk))
        self.assertEqual(api_as(joiner).get('/api/auth/me').json()['role'], 'front')

        detail = self.client.get(f'/api/projects/{self.project.pk}').json()
        self.assertEqual(detail['invitations'], [])  # 받은 초대는 대기 목록에서 빠짐
        self.assertIn('새 대원', [m['name'] for m in detail['members']])

    def test_accept_needs_login(self):
        token = self.invite().json()['token']
        self.assertEqual(APIClient().post(f'/api/invitations/{token}/accept').status_code, 401)

    def test_expired_link_says_so(self):
        token = self.invite().json()['token']
        ProjectInvitation.objects.filter(token=token).update(expires_at=timezone.now() - timedelta(seconds=1))
        res = api_as(make_user('late@example.com')).post(f'/api/invitations/{token}/accept')
        self.assertEqual(res.status_code, 410)
        self.assertEqual(res.json()['code'], 'invitation_expired')
        self.assertEqual(APIClient().get(f'/api/invitations/{token}').json()['status'], 'expired')

    def test_member_cannot_invite(self):
        member = add_to(self.project, 'front@example.com', 'front')
        res = api_as(member.user).post(f'/api/projects/{self.project.pk}/invitations', {}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'message': '리더만 할 수 있어요', 'code': 'leader_only'})

    def test_unknown_role_id(self):
        res = self.invite(roleIds=[999999])
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['code'], 'role_not_found')

    def test_revoke(self):
        inv_id = self.invite(email='later@example.com').json()['id']
        res = self.client.post(f'/api/projects/{self.project.pk}/invitations/{inv_id}/revoke')
        self.assertEqual(res.json()['status'], 'revoked')
        self.assertEqual(self.client.get(f'/api/projects/{self.project.pk}').json()['invitations'], [])

    def test_unknown_token_preview(self):
        res = APIClient().get('/api/invitations/nope')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['code'], 'invitation_not_found')


class AdminTests(TestCase):
    def test_admin_pages_open(self):
        admin = make_user('admin@example.com')
        admin.is_staff = admin.is_superuser = True
        admin.save()
        project, _ = make_project(leader=admin)
        ProjectInvitation.objects.create(project=project, invited_by=admin)
        self.client.force_login(admin)
        for url in ['/admin/projects/project/', f'/admin/projects/project/{project.pk}/change/',
                    '/admin/projects/projectmember/', '/admin/projects/projectinvitation/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Project.objects.count(), 1)
