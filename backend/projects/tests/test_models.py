from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from config.testing import ErdContractMixin
from projects.models import (
    InvitationRole, Project, ProjectInvitation, ProjectMember, ProjectMemberRole, ProjectRole,
)
from projects.testing import make_project, make_user


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [
        (Project, set()), (ProjectRole, set()), (ProjectMember, set()), (ProjectMemberRole, set()),
        (ProjectInvitation, set()), (InvitationRole, set()),
    ]


class ConstraintTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()

    def assertRejected(self, make):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make()

    def test_role_label_is_unique_in_a_project(self):
        self.assertRejected(lambda: ProjectRole.objects.create(project=self.project, label='디자인'))

    def test_each_basic_role_once_per_project(self):
        self.assertRejected(lambda: ProjectRole.objects.create(project=self.project, label='디자인2', role_key='design'))

    def test_many_custom_roles_without_key_are_fine(self):
        ProjectRole.objects.create(project=self.project, label='기획')
        ProjectRole.objects.create(project=self.project, label='QA')
        self.assertEqual(self.project.roles.filter(role_key__isnull=True).count(), 2)

    def test_unknown_role_key_status_unit_and_negative_headcount(self):
        self.assertRejected(lambda: ProjectRole.objects.create(project=self.project, label='PM', role_key='pm'))
        self.assertRejected(lambda: ProjectRole.objects.create(project=self.project, label='음수', headcount=-1))
        self.assertRejected(lambda: Project.objects.filter(pk=self.project.pk).update(status='flying'))
        self.assertRejected(lambda: Project.objects.filter(pk=self.project.pk).update(schedule_unit='week'))

    def test_one_member_row_per_person(self):
        self.assertRejected(lambda: ProjectMember.objects.create(project=self.project, user=self.leader))

    def test_invitation_defaults(self):
        inv = ProjectInvitation.objects.create(project=self.project, invited_by=self.leader)
        self.assertEqual(len(inv.token), 64)
        self.assertEqual(inv.status, 'pending')
        self.assertAlmostEqual(inv.expires_at, timezone.now() + timedelta(days=7), delta=timedelta(seconds=5))

    def test_deleting_project_removes_roles_members_and_invitations(self):
        ProjectInvitation.objects.create(project=self.project, invited_by=self.leader)
        self.project.delete()
        self.assertFalse(ProjectRole.objects.exists())
        self.assertFalse(ProjectMember.objects.exists())
        self.assertFalse(ProjectMemberRole.objects.exists())
        self.assertFalse(ProjectInvitation.objects.exists())

    def test_user_who_created_a_project_cannot_be_deleted(self):
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.leader.delete()

    def test_other_user_can_be_deleted_and_leaves_the_project(self):
        other = make_user('bye@example.com')
        ProjectMember.objects.create(project=self.project, user=other)
        other.delete()
        self.assertEqual(self.project.members.count(), 1)
