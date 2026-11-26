from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from projects import services
from projects.errors import Conflict, Forbidden, Gone, NotFound
from projects.models import ProjectInvitation, ProjectRole
from projects.testing import add_to, make_project, make_user
from workspaces.models import WorkspaceMember
from workspaces.services import create_workspace


class CreateProjectTests(TestCase):
    def test_default_roles_and_leader(self):
        project, leader = make_project(leader_role='back')
        self.assertEqual([(r.role_key, r.label, r.headcount) for r in project.roles.all()],
                         [('design', '디자인', 1), ('front', '프론트', 1), ('back', '백', 1)])
        member = services.membership(leader, project)
        self.assertTrue(member.is_leader)
        self.assertEqual(services.role_keys(member), ['back'])

    def test_custom_roles_keep_order_and_leader_can_take_a_custom_role(self):
        roles = [{'role_key': None, 'label': '기획', 'headcount': 1}, {'role_key': 'design', 'label': '디자인', 'headcount': 2}]
        project, leader = make_project(roles=roles, leader_role='기획')
        self.assertEqual([r.label for r in project.roles.all()], ['기획', '디자인'])
        member = services.membership(leader, project)
        self.assertEqual([r.label for r in services.roles_of(member)], ['기획'])
        self.assertEqual(services.role_keys(member), [])  # 기본 역할이 아니라서 키는 없음

    def test_new_user_gets_a_personal_workspace(self):
        project, leader = make_project()
        self.assertEqual(project.workspace.name, '리더의 스페이스')
        self.assertTrue(WorkspaceMember.objects.filter(workspace=project.workspace, user=leader, permission_role='owner').exists())

    def test_cannot_create_in_someone_elses_workspace(self):
        owner = make_user('owner@example.com')
        stranger = make_user('stranger@example.com')
        ws = create_workspace(owner, '남의 팀')
        with self.assertRaises(Forbidden):
            services.create_project(stranger, name='몰래', deadline_at=timezone.now(), workspace=ws)


class CurrentProjectTests(TestCase):
    def test_latest_joined_project_is_current(self):
        older, leader = make_project(name='예전 원정대')
        newer, _ = make_project(leader=leader, name='새 원정대', leader_role='front')
        self.assertEqual(services.current_project(leader), newer)
        self.assertEqual(services.primary_role_key(leader), 'front')

    def test_no_project(self):
        user = make_user('alone@example.com')
        self.assertIsNone(services.current_project(user))
        self.assertIsNone(services.primary_role_key(user))

    def test_first_basic_role_in_role_order(self):
        project, _ = make_project()
        member = add_to(project, 'both@example.com', 'back', 'design')
        self.assertEqual(services.role_keys(member), ['design', 'back'])


class JoinTests(TestCase):
    def test_join_adds_workspace_membership_and_roles_once(self):
        project, _ = make_project()
        member = add_to(project, 'front@example.com', 'front')
        services.join_project(member.user, project, project.roles.filter(role_key='front'))  # 다시 들어와도
        self.assertTrue(WorkspaceMember.objects.filter(workspace=project.workspace, user=member.user, permission_role='member').exists())
        self.assertEqual(services.role_keys(member), ['front'])

    def test_role_from_another_project_is_rejected(self):
        project, leader = make_project()
        other, _ = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        with self.assertRaises(Conflict):
            services.join_project(make_user('x@example.com'), project, other.roles.all())


class InvitationTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()
        self.front = self.project.roles.get(role_key='front')

    def invite(self, **kw):
        return services.create_invitation(self.leader, self.project, **kw)

    def test_email_invitation_flow(self):
        inv = self.invite(email='Front@Example.com', roles=[self.front])
        self.assertEqual(inv.email, 'front@example.com')
        user = make_user('front@example.com')
        member = services.accept_invitation(inv.token, user)
        self.assertEqual(services.role_keys(member), ['front'])
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.accepted_by), ('accepted', user))
        self.assertEqual(services.current_project(user), self.project)

    def test_accepting_twice_is_harmless_for_the_same_person(self):
        inv = self.invite(roles=[self.front])
        user = make_user('someone@example.com')
        first = services.accept_invitation(inv.token, user)
        self.assertEqual(services.accept_invitation(inv.token, user), first)

    def test_link_invitation_is_single_use(self):
        inv = self.invite()
        services.accept_invitation(inv.token, make_user('a@example.com'))
        with self.assertRaises(Conflict):
            services.accept_invitation(inv.token, make_user('b@example.com'))

    def test_email_invitation_needs_that_account(self):
        inv = self.invite(email='right@example.com')
        with self.assertRaises(Forbidden):
            services.accept_invitation(inv.token, make_user('wrong@example.com'))

    def test_only_leader_invites(self):
        member = add_to(self.project, 'front@example.com', 'front')
        with self.assertRaises(Forbidden):
            services.create_invitation(member.user, self.project)

    def test_cannot_invite_an_existing_member_by_email(self):
        with self.assertRaises(Conflict):
            self.invite(email='leader@example.com')

    def test_existing_member_does_not_use_up_a_link(self):
        inv = self.invite()
        with self.assertRaises(Conflict):
            services.accept_invitation(inv.token, self.leader)
        inv.refresh_from_db()
        self.assertEqual(inv.status, 'pending')

    def test_expired_invitation(self):
        inv = self.invite()
        ProjectInvitation.objects.filter(pk=inv.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaises(Gone):
            services.accept_invitation(inv.token, make_user('late@example.com'))
        inv.refresh_from_db()
        self.assertEqual(inv.status, 'expired')

    def test_revoked_invitation(self):
        inv = services.revoke_invitation(self.leader, self.invite())
        self.assertEqual(inv.status, 'revoked')
        with self.assertRaises(Gone):
            services.accept_invitation(inv.token, make_user('late@example.com'))
        with self.assertRaises(Conflict):
            services.revoke_invitation(self.leader, inv)

    def test_unknown_token(self):
        with self.assertRaises(NotFound):
            services.accept_invitation('nope', make_user('who@example.com'))

    def test_invitation_roles_must_be_from_this_project(self):
        other, _ = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        with self.assertRaises(Conflict):
            self.invite(roles=list(other.roles.all()))

    def test_invitation_roles_listed_in_role_order(self):
        back, design = self.project.roles.get(role_key='back'), self.project.roles.get(role_key='design')
        inv = self.invite(roles=[back, design])
        self.assertEqual([r.role_key for r in services.invitation_roles(inv)], ['design', 'back'])
        self.assertIsInstance(inv.project.roles.first(), ProjectRole)
