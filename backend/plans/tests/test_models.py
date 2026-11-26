from importlib import import_module

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.test import TestCase

from config.testing import ErdContractMixin
from plans.models import BASE_CAMP_NAME, Checkpoint
from projects.testing import make_project, make_user


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Checkpoint, set())]


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
