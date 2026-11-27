from importlib import import_module

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, RestrictedError
from django.test import TestCase

from config.testing import ErdContractMixin
from plans.models import BASE_CAMP_NAME, Checkpoint, CheckpointTask, PlanDocument
from projects.testing import add_to, make_project, make_user


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Checkpoint, set()), (PlanDocument, set()), (CheckpointTask, set())]


class BaseCampTests(TestCase):
    def test_new_project_gets_a_base_camp(self):
        project, _ = make_project()
        camp = Checkpoint.objects.get(project=project, seq=0)
        self.assertEqual((camp.name, camp.source), (BASE_CAMP_NAME, 'plan'))
        self.assertEqual(project.checkpoints.count(), 1)

    def test_each_project_has_its_own(self):
        make_project()
        make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        self.assertEqual(Checkpoint.objects.filter(seq=0).count(), 2)

    def test_migration_backfill_adds_only_missing_ones(self):
        have, _ = make_project()
        missing, _ = make_project(leader=make_user('l2@example.com'), name='예전 원정대')
        Checkpoint.objects.filter(project=missing).delete()  # 예전에 만든 원정대처럼
        backfill = import_module('plans.migrations.0001_initial').add_base_camps
        backfill(django_apps, None)
        backfill(django_apps, None)  # 두 번 해도 한 개씩
        self.assertEqual(Checkpoint.objects.filter(project=have, seq=0).count(), 1)
        self.assertEqual(Checkpoint.objects.filter(project=missing, seq=0).count(), 1)


class ConstraintTests(TestCase):
    def setUp(self):
        self.project, _ = make_project()

    def assertRejected(self, make):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make()

    def test_seq_is_unique_in_a_project(self):
        Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        self.assertRejected(lambda: Checkpoint.objects.create(project=self.project, seq=1, name='또 로그인'))
        self.assertRejected(lambda: Checkpoint.objects.create(project=self.project, seq=0, name='두 번째 베이스 캠프'))

    def test_same_seq_in_another_project_is_fine(self):
        other, _ = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        Checkpoint.objects.create(project=other, seq=1, name='로그인')

    def test_source_must_be_known(self):
        self.assertRejected(lambda: Checkpoint.objects.create(project=self.project, seq=1, name='로그인', source='robot'))
        for seq, source in enumerate(('plan', 'ai', 'manual'), start=1):
            Checkpoint.objects.create(project=self.project, seq=seq, name=source, source=source)

    def test_listed_in_seq_order(self):
        Checkpoint.objects.create(project=self.project, seq=2, name='메인 피드')
        Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        self.assertEqual(list(self.project.checkpoints.values_list('seq', flat=True)), [0, 1, 2])

    def test_deleting_the_project_deletes_its_checkpoints(self):
        Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        self.project.delete()
        self.assertEqual(Checkpoint.objects.count(), 0)


class PlanDocumentTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()

    def doc(self, **kw):
        return PlanDocument.objects.create(**{'project': self.project, 'uploaded_by': self.leader, 'source_type': 'file', **kw})

    def test_each_source_type_is_accepted_and_starts_as_current(self):
        for source_type in ('file', 'link', 'text'):
            self.assertTrue(self.doc(source_type=source_type).is_current)

    def test_unknown_source_type_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.doc(source_type='fax')

    def test_file_columns_round_trip(self):
        doc = self.doc(file_name='캠퍼스앱_기획안_v3.pdf', file_size=5_000_000_000, mime_type='application/pdf', page_count=12, storage_url='plans/1/a1b2.pdf')
        doc.refresh_from_db()
        self.assertEqual((doc.file_name, doc.file_size, doc.page_count), ('캠퍼스앱_기획안_v3.pdf', 5_000_000_000, 12))
        self.assertIsNone(doc.text_content)

    def test_deleting_the_project_deletes_its_documents(self):
        self.doc()
        self.project.delete()
        self.assertEqual(PlanDocument.objects.count(), 0)

    def test_an_uploader_with_documents_cannot_be_deleted(self):
        uploader = make_user('uploader@example.com')
        self.doc(uploaded_by=uploader)
        with self.assertRaises(ProtectedError):
            uploader.delete()


class CheckpointTaskTests(TestCase):
    def setUp(self):
        self.project, _ = make_project()
        self.checkpoint = Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        self.role = self.project.roles.get(role_key='front')

    def task(self, **kw):
        data = {'checkpoint': self.checkpoint, 'role': self.role, 'title': '로그인 폼 화면 만들기', 'origin': 'plan', 'state': 'selected'}
        return CheckpointTask.objects.create(**{**data, **kw})

    def assertRejected(self, make):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make()

    def test_every_origin_and_state_is_accepted(self):
        for origin in ('plan', 'ai', 'manual'):
            self.task(origin=origin)
        for state in ('suggested', 'selected', 'done', 'dismissed'):
            self.task(state=state)
        self.assertEqual(self.checkpoint.tasks.count(), 7)

    def test_unknown_origin_or_state_is_rejected(self):
        self.assertRejected(lambda: self.task(origin='robot'))
        self.assertRejected(lambda: self.task(state='half-done'))

    def test_a_role_with_tasks_cannot_be_deleted_on_its_own(self):
        self.task()
        with self.assertRaises(RestrictedError):
            self.role.delete()

    def test_the_whole_project_can_still_be_deleted_with_tasks(self):
        self.task()
        self.project.delete()  # 할 일이 구간과 같이 지워지니까 역할 RESTRICT 에 안 걸려요 (PROTECT 였다면 막혔음)
        self.assertEqual(CheckpointTask.objects.count(), 0)

    def test_assignee_is_cleared_when_the_member_leaves(self):
        member = add_to(self.project, 'front@example.com', 'front')
        task = self.task(assignee_member=member)
        member.delete()
        task.refresh_from_db()
        self.assertIsNone(task.assignee_member_id)

    def test_deleting_a_checkpoint_deletes_its_tasks(self):
        self.task()
        self.checkpoint.delete()
        self.assertEqual(CheckpointTask.objects.count(), 0)
