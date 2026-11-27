from django.test import TestCase
from django.utils import timezone

from plans import services
from plans.models import BASE_CAMP_NAME, Checkpoint
from projects.testing import make_project, make_user


def add_screens(project, *names):
    """화면 구간 1, 2, 3 … 을 순서대로 만들어요."""
    return [Checkpoint.objects.create(project=project, seq=i, name=n) for i, n in enumerate(names, start=1)]


def finish(*checkpoints):
    for c in checkpoints:
        Checkpoint.objects.filter(pk=c.pk).update(completed_at=timezone.now())


class CurrentCheckpointTests(TestCase):
    def setUp(self):
        self.project, _ = make_project()

    def seq(self):
        return services.current_checkpoint(self.project).seq

    def test_base_camp_when_there_are_no_screens_yet(self):
        current = services.current_checkpoint(self.project)
        self.assertEqual((current.seq, current.name), (0, BASE_CAMP_NAME))

    def test_first_screen_when_nothing_is_finished(self):
        add_screens(self.project, '로그인', '메인 피드', '마이페이지')
        self.assertEqual(self.seq(), 1)  # 프론트의 기본값(CURRENT_CHECKPOINT = 1)과 같아요

    def test_moves_on_only_when_a_screen_is_finished(self):
        login, feed, _ = add_screens(self.project, '로그인', '메인 피드', '마이페이지')
        finish(login)
        self.assertEqual(self.seq(), 2)
        finish(feed)
        self.assertEqual(self.seq(), 3)

    def test_arriving_does_not_move_it(self):
        _, feed = add_screens(self.project, '로그인', '메인 피드')
        Checkpoint.objects.filter(pk=feed.pk).update(arrived_at=timezone.now())
        self.assertEqual(self.seq(), 1)

    def test_lowest_unfinished_wins_when_screens_overlap(self):
        login, feed, _ = add_screens(self.project, '로그인', '메인 피드', '마이페이지')
        finish(feed)  # 2번이 먼저 끝나도 1번이 남아 있으면 1번
        self.assertEqual(self.seq(), 1)

    def test_last_screen_when_all_are_finished(self):
        screens = add_screens(self.project, '로그인', '메인 피드')
        finish(*screens)
        self.assertEqual(self.seq(), 2)

    def test_base_camp_being_finished_changes_nothing(self):
        add_screens(self.project, '로그인')
        finish(services.checkpoint_by_seq(self.project, 0))
        self.assertEqual(self.seq(), 1)

    def test_base_camp_is_brought_back_if_it_was_deleted(self):
        Checkpoint.objects.filter(project=self.project).delete()
        current = services.current_checkpoint(self.project)
        self.assertEqual((current.seq, current.name), (0, BASE_CAMP_NAME))
        self.assertEqual(self.project.checkpoints.count(), 1)

    def test_other_projects_do_not_leak(self):
        other, _ = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        finish(*add_screens(other, '로그인', '메인 피드'))
        add_screens(self.project, '지도')
        self.assertEqual(self.seq(), 1)
        self.assertEqual(services.current_checkpoint(other).project_id, other.pk)

    def test_every_call_returns_a_checkpoint_of_that_project(self):
        add_screens(self.project, '로그인')
        self.assertEqual(services.current_checkpoint(self.project).project_id, self.project.pk)


class CheckpointBySeqTests(TestCase):
    def setUp(self):
        self.project, _ = make_project()
        self.login, self.feed = add_screens(self.project, '로그인', '메인 피드')

    def test_finds_by_the_front_end_number(self):
        self.assertEqual(services.checkpoint_by_seq(self.project, 0).name, BASE_CAMP_NAME)
        self.assertEqual(services.checkpoint_by_seq(self.project, 1), self.login)
        self.assertEqual(services.checkpoint_by_seq(self.project, 2), self.feed)

    def test_unknown_number_is_none(self):
        self.assertIsNone(services.checkpoint_by_seq(self.project, 3))
        self.assertIsNone(services.checkpoint_by_seq(self.project, -1))

    def test_does_not_look_into_other_projects(self):
        other, _ = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        self.assertIsNone(services.checkpoint_by_seq(other, 1))
