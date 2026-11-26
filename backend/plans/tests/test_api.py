"""기획안 · 루트 API — 프론트 api.plan · api.files.uploadPlan · api.route.recommend 와 팀 변경 11/26."""
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from config.testing import ErdContractMixin
from plans.models import Checkpoint, CheckpointTask, PlanDocument
from projects.models import Project
from projects.testing import add_to, api_as, make_project, make_user

TMP_MEDIA = tempfile.mkdtemp()


def plan_body(**over):
    date = (timezone.localdate() + timedelta(days=14)).isoformat()
    body = {
        'unit': 'day', 'date': date, 'time': '18:00',
        'roles': [
            {'id': 'r1', 'label': '디자인', 'people': 1, 'role': 'design'},
            {'id': 'r2', 'label': '프론트', 'people': 1, 'role': 'front'},
            {'id': 'r3', 'label': '백', 'people': 1, 'role': 'back'},
        ],
        'checkpoints': [{'id': 'c1', 'name': '로그인'}, {'id': 'c2', 'name': '메인 피드'}, {'id': 'c3', 'name': '마이페이지'}],
    }
    body.update(over)
    return body


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(PlanDocument, set()), (Checkpoint, set()), (CheckpointTask, set())]


class PlanTests(TestCase):
    def setUp(self):
        self.user = make_user('solo@example.com', '솔로')
        self.api = api_as(self.user)

    def test_get_without_project_returns_default_plan(self):
        res = self.api.get('/api/plan')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['checkpoints'], [])

    def test_put_creates_project_with_checkpoints_and_base_camp(self):
        res = self.api.put('/api/plan', plan_body(), format='json')
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual([c['name'] for c in body['checkpoints']], ['로그인', '메인 피드', '마이페이지'])
        project = Project.objects.get()
        self.assertTrue(project.checkpoints.filter(seq=0).exists())  # 베이스 캠프
        # 일정이 자동으로 나뉘고 마지막 구간은 마감에 끝나요
        last = project.checkpoints.order_by('-seq').first()
        self.assertEqual(last.end_at, project.deadline_at)
        self.assertIn('남음', body['remaining']['text'])

    def test_hour_unit_shows_hours_left(self):
        today = timezone.localdate().isoformat()
        later = (timezone.localtime() + timedelta(hours=6)).strftime('%H:00')
        if later < timezone.localtime().strftime('%H:%M'):  # 자정을 넘기면 내일로
            today = (timezone.localdate() + timedelta(days=1)).isoformat()
        res = self.api.put('/api/plan', plan_body(unit='hour', date=today, time=later), format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['remaining']['text'].endswith('시간 남음'))
        self.assertEqual(Project.objects.get().schedule_unit, 'hour')

    def test_edit_keeps_checkpoint_rows_and_renames(self):
        self.api.put('/api/plan', plan_body(), format='json')
        ids = list(Checkpoint.objects.filter(seq__gt=0).order_by('seq').values_list('pk', flat=True))
        res = self.api.put('/api/plan', plan_body(checkpoints=[
            {'id': str(ids[0]), 'name': '로그인'}, {'id': str(ids[1]), 'name': '피드'},
        ]), format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(list(Checkpoint.objects.filter(seq__gt=0).order_by('seq').values_list('pk', 'name')), [(ids[0], '로그인'), (ids[1], '피드')])

    def test_too_many_checkpoints(self):
        res = self.api.put('/api/plan', plan_body(checkpoints=[{'name': f'화면{i}'} for i in range(9)]), format='json')
        self.assertEqual(res.status_code, 400)

    def test_duplicate_role_labels_rejected(self):
        roles = [{'label': '디자인', 'people': 1}, {'label': '디자인', 'people': 1}]
        self.assertEqual(self.api.put('/api/plan', plan_body(roles=roles), format='json').status_code, 400)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class DocumentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.project, self.leader = make_project()
        self.api = api_as(self.leader)

    def test_empty_state_message(self):
        res = self.api.get('/api/plan/document')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['message'], '아직 기획 문서가 없어요')

    def test_edit_text_then_history(self):
        self.api.put('/api/plan/document', {'text': '첫 기획\n- 로그인'}, format='json')
        res = self.api.put('/api/plan/document', {'text': '고친 기획\n- 로그인\n- 피드'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn('고친 기획', res.json()['text'])
        self.assertEqual(PlanDocument.objects.filter(project=self.project, is_current=True).count(), 1)
        self.assertEqual(len(self.api.get('/api/plan/documents').json()), 2)

    def test_clear_document_returns_empty_state(self):
        self.api.put('/api/plan/document', {'text': '기획'}, format='json')
        res = self.api.delete('/api/plan/document')
        self.assertEqual(res.json()['message'], '아직 기획 문서가 없어요')

    def test_upload_and_download_file(self):
        upload = SimpleUploadedFile('plan.txt', '로그인 화면\n메인 피드 화면'.encode(), content_type='text/plain')
        res = self.api.post('/api/files/plan', {'file': upload}, format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        file_id = res.json()['id']
        download = self.api.get(f'/api/files/plan/{file_id}')
        self.assertEqual(download.status_code, 200)

    def test_other_project_cannot_download(self):
        upload = SimpleUploadedFile('plan.txt', b'login', content_type='text/plain')
        file_id = self.api.post('/api/files/plan', {'file': upload}, format='multipart').json()['id']
        _, stranger = make_project(make_user('other@example.com'), name='다른 팀')
        self.assertEqual(api_as(stranger).get(f'/api/files/plan/{file_id}').status_code, 404)

    def test_rejects_unknown_file_type(self):
        upload = SimpleUploadedFile('plan.exe', b'MZ', content_type='application/octet-stream')
        self.assertEqual(self.api.post('/api/files/plan', {'file': upload}, format='multipart').status_code, 400)


class RouteTests(TestCase):
    def setUp(self):
        self.user = make_user('solo@example.com', '솔로')
        self.api = api_as(self.user)

    def recommend(self, text):
        deadline = {'date': (timezone.localdate() + timedelta(days=10)).isoformat(), 'time': '18:00', 'unit': 'day'}
        return self.api.post('/api/route/recommend', {
            'deadline': deadline, 'roles': plan_body()['roles'], 'source': {'type': 'text', 'text': text},
        }, format='json')

    def test_recommend_puts_login_first(self):
        res = self.recommend('메인 피드 화면\n마이페이지\n로그인 화면')
        self.assertEqual(res.status_code, 200, res.content)
        names = [c['name'] for c in res.json()['checkpoints']]
        self.assertEqual(names[0], '로그인')
        self.assertIn('마이페이지', names)

    def test_recommend_falls_back_to_ai_list(self):
        res = self.recommend('그냥 멋진 앱')
        picks = res.json()['checkpoints']
        self.assertTrue(picks)
        self.assertTrue(all(c.get('source') == 'ai' for c in picks))


class TaskTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()
        self.front = add_to(self.project, 'front@example.com', 'front', name='프론트').user
        api_as(self.leader).put('/api/plan', plan_body(), format='json')

    def test_start_route_suggests_tasks_and_progress(self):
        res = api_as(self.leader).post('/api/route/start')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, 'climbing')
        self.assertTrue(CheckpointTask.objects.filter(checkpoint__project=self.project).exists())

    def test_member_cannot_add_task_for_other_role(self):
        res = api_as(self.front).post('/api/checkpoints/1/tasks', {'role': 'design', 'title': '시안'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_member_adds_and_completes_own_task(self):
        api = api_as(self.front)
        res = api.post('/api/checkpoints/1/tasks', {'role': 'front', 'title': '로그인 폼'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        task_id = res.json()['id']
        done = api.patch(f'/api/tasks/{task_id}', {'state': 'done'}, format='json')
        self.assertEqual(done.json()['state'], 'done')

    def test_leader_edits_checkpoint_hours(self):
        start = timezone.localtime().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        res = api_as(self.leader).patch('/api/checkpoints/1', {'startAt': start.isoformat(), 'endAt': (start + timedelta(hours=5)).isoformat()}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        cp = Checkpoint.objects.get(project=self.project, seq=1)
        self.assertEqual(cp.end_at - cp.start_at, timedelta(hours=5))

    def test_member_cannot_edit_dates(self):
        now = timezone.now()
        res = api_as(self.front).patch('/api/checkpoints/1', {'startAt': now.isoformat(), 'endAt': (now + timedelta(hours=2)).isoformat()}, format='json')
        self.assertEqual(res.status_code, 403)
