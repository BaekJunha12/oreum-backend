from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from plans.models import Checkpoint, PlanDocument
from plans.services import set_current_document
from projects.models import Project
from projects.services import current_project, is_leader
from projects.testing import add_to, api_as, make_project, make_user

URL = '/api/route/recommend'
DEMO = [{'id': 'r1', 'name': '로그인'}, {'id': 'r2', 'name': '메인 피드'}, {'id': 'r3', 'name': '마이페이지'}, {'id': 'r4', 'name': '알림'}]


def body(**changes):
    """프론트 RouteRecommendInput — 시작하기의 기본 값과 같은 모양."""
    data = {
        'deadline': {'date': '2026-12-03', 'time': '18:00', 'unit': 'day'},
        'roles': [
            {'id': 'design', 'label': '디자인', 'people': 2, 'role': 'design'},
            {'id': 'front', 'label': '프론트', 'people': 2, 'role': 'front'},
            {'id': 'back', 'label': '백', 'people': 2, 'role': 'back'},
        ],
        'source': {'type': 'file', 'name': '캠퍼스앱_기획안_v3.pdf'},
    }
    return {**data, **changes}


class RouteRecommendApiTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()
        self.client = api_as(self.leader)

    def post(self, data=None, client=None):
        return (client or self.client).post(URL, data if data is not None else body(), format='json')

    def document(self, **fields):
        return set_current_document(self.project, self.leader, **{'source_type': 'file', 'file_name': '기획안.pdf', **fields})

    # ───── 결과 ─────

    def test_answers_with_the_front_end_route_shape(self):
        res = self.post()
        self.assertEqual(res.status_code, 200, res.json())
        self.assertEqual(res.json(), {'checkpoints': DEMO})

    def test_at_most_eight_checkpoints(self):
        with mock.patch('plans.services.DEMO_ROUTE', [f'화면 {i}' for i in range(10)]):
            checkpoints = self.post().json()['checkpoints']
        self.assertEqual([c['name'] for c in checkpoints], [f'화면 {i}' for i in range(8)])

    def test_it_only_recommends_and_saves_no_checkpoints(self):
        self.post()
        self.assertEqual(list(self.project.checkpoints.values_list('seq', flat=True)), [0])  # 베이스 캠프뿐

    # ───── 기획안 (파일) ─────

    def test_uploaded_file_is_found_by_its_id(self):
        doc = self.document()
        res = self.post(body(source={'type': 'file', 'name': '기획안.pdf', 'fileId': str(doc.pk)}))
        self.assertEqual(res.status_code, 200, res.json())
        self.assertEqual(PlanDocument.objects.count(), 1)  # 새 기록 없음

    def test_unknown_or_foreign_file_id_is_404(self):
        other, other_leader = make_project(leader=make_user('l2@example.com'), name='다른 원정대')
        theirs = set_current_document(other, other_leader, source_type='file', file_name='남의 기획안.pdf')
        link = self.document(source_type='link', file_name=None, link_url='https://example.com/plan')  # 파일이 아닌 기록
        for file_id in ['999999', str(theirs.pk), str(link.pk), 'abc', '²', '99999999999999999999']:
            res = self.post(body(source={'type': 'file', 'name': 'x.pdf', 'fileId': file_id}))
            self.assertEqual((res.status_code, res.json()['code']), (404, 'plan_file_not_found'), file_id)

    def test_file_name_only_is_fine(self):
        self.assertEqual(self.post(body(source={'type': 'file', 'name': '예시 기획안.pdf'})).status_code, 200)
        self.assertEqual(PlanDocument.objects.count(), 0)

    # ───── 기획안 (링크 · 글) ─────

    def test_link_is_recorded_as_the_current_document(self):
        old = self.document()
        res = self.post(body(source={'type': 'link', 'url': '  https://example.com/plan  '}))
        self.assertEqual(res.status_code, 200, res.json())
        doc = PlanDocument.objects.get(is_current=True)
        self.assertEqual((doc.source_type, doc.link_url, doc.uploaded_by, doc.project), ('link', 'https://example.com/plan', self.leader, self.project))
        old.refresh_from_db()
        self.assertFalse(old.is_current)

    def test_text_is_recorded_trimmed_and_cut_to_the_limit(self):
        self.post(body(source={'type': 'text', 'text': '  로그인 · 피드 · 마이페이지  '}))
        self.assertEqual(PlanDocument.objects.get().text_content, '로그인 · 피드 · 마이페이지')
        with mock.patch('plans.services.TEXT_LIMIT', 4):
            self.post(body(source={'type': 'text', 'text': '가나다라마바사'}))
        self.assertEqual(PlanDocument.objects.get(is_current=True).text_content, '가나다라')

    def test_asking_again_with_the_same_link_or_text_adds_nothing(self):
        for source in ({'type': 'link', 'url': 'https://example.com/plan'}, {'type': 'text', 'text': '기획 내용입니다 로그인'}):
            first = self.post(body(source=source))
            again = self.post(body(source=source))  # "추천으로 되돌리기"
            self.assertEqual(first.json(), again.json())
        self.assertEqual(PlanDocument.objects.count(), 2)  # 링크 하나, 글 하나
        self.assertEqual(PlanDocument.objects.filter(is_current=True).count(), 1)

    def test_a_different_link_replaces_the_current_one(self):
        self.post(body(source={'type': 'link', 'url': 'https://example.com/v1'}))
        self.post(body(source={'type': 'link', 'url': 'https://example.com/v2'}))
        self.assertEqual(list(PlanDocument.objects.order_by('id').values_list('link_url', 'is_current')), [('https://example.com/v1', False), ('https://example.com/v2', True)])

    # ───── 잘못된 입력 ─────

    def assertInvalid(self, data, message):
        res = self.post(data)
        self.assertEqual(res.status_code, 400, res.json())
        self.assertIn(message, res.json()['message'])
        self.assertEqual(PlanDocument.objects.count(), 0)

    def test_bad_links(self):
        for url in ['', 'ftp://example.com/plan', 'example.com', 'https://nodot', 'https://exa mple.com']:
            self.assertInvalid(body(source={'type': 'link', 'url': url}), '기획안 링크는 https://')

    def test_empty_text(self):
        self.assertInvalid(body(source={'type': 'text', 'text': '   '}), '기획 내용을 적어 주세요')

    def test_unknown_source_type_or_missing_parts(self):
        self.assertInvalid(body(source={'type': 'fax'}), 'source.type')
        data = body()
        del data['source']
        self.assertInvalid(data, 'source')

    def test_bad_deadline(self):
        self.assertInvalid(body(deadline={'date': '2026-13-45', 'time': '18:00', 'unit': 'day'}), 'deadline.date')
        self.assertInvalid(body(deadline={'date': '2026-12-03', 'time': '25:99', 'unit': 'day'}), 'deadline.time')
        self.assertInvalid(body(deadline={'date': '2026-12-03', 'time': '18:00', 'unit': 'week'}), 'deadline.unit')
        self.assertInvalid(body(deadline={'date': '', 'time': '18:00', 'unit': 'day'}), 'deadline.date')

    def test_bad_roles(self):
        dup = [{'label': '디자인', 'people': 1}, {'label': '디자인', 'people': 1}]
        self.assertInvalid(body(roles=dup), '역할 이름이 겹쳐요')
        two_design = [{'label': '디자인1', 'people': 1, 'role': 'design'}, {'label': '디자인2', 'people': 1, 'role': 'design'}]
        self.assertInvalid(body(roles=two_design), '한 번씩만')
        self.assertInvalid(body(roles=[{'label': '디자인', 'people': 21}]), 'people')

    # ───── 누가 ─────

    def test_needs_login(self):
        self.assertEqual(self.post(client=APIClient()).status_code, 401)

    def test_only_the_leader_asks(self):
        member = add_to(self.project, 'front@example.com', 'front')
        res = self.post(body(source={'type': 'link', 'url': 'https://example.com/plan'}), client=api_as(member.user))
        self.assertEqual((res.status_code, res.json()), (403, {'message': '리더만 할 수 있어요', 'code': 'leader_only'}))
        self.assertEqual(PlanDocument.objects.count(), 0)

    # ───── 원정대가 아직 없을 때 ─────

    def test_without_a_project_one_is_made_from_the_request(self):
        user = make_user('new@example.com', '새 사용자')
        data = body(
            deadline={'date': '2026-12-03', 'time': '18:00', 'unit': 'hour'},
            roles=[{'id': 'a', 'label': '디자인', 'people': 2, 'role': 'design'}, {'id': 'b', 'label': '기획', 'people': 1}],
            source={'type': 'link', 'url': 'https://example.com/plan'},
        )
        res = self.post(data, client=api_as(user))
        self.assertEqual(res.status_code, 200, res.json())
        project = current_project(user)
        deadline = timezone.localtime(project.deadline_at)
        self.assertEqual((deadline.year, deadline.month, deadline.day, deadline.hour, deadline.minute), (2026, 12, 3, 18, 0))
        self.assertEqual((project.schedule_unit, is_leader(user, project)), ('hour', True))
        self.assertEqual([(r.label, r.headcount, r.role_key) for r in project.roles.all()], [('디자인', 2, 'design'), ('기획', 1, None)])
        self.assertEqual(PlanDocument.objects.get().project, project)
        self.assertTrue(Checkpoint.objects.filter(project=project, seq=0).exists())

    def test_an_unknown_file_id_does_not_leave_a_new_project_behind(self):
        user = make_user('new@example.com', '새 사용자')
        res = self.post(body(source={'type': 'file', 'name': 'x.pdf', 'fileId': '1'}), client=api_as(user))
        self.assertEqual(res.status_code, 404)
        self.assertIsNone(current_project(user))
        self.assertFalse(Project.objects.filter(created_by=user).exists())

    def test_an_existing_project_is_not_changed_by_asking(self):
        before = (self.project.deadline_at, self.project.schedule_unit, list(self.project.roles.values_list('label', 'headcount')))
        self.post(body(deadline={'date': '2027-01-01', 'time': '09:00', 'unit': 'hour'}, roles=[{'label': '기획', 'people': 5}]))
        self.project.refresh_from_db()
        after = (self.project.deadline_at, self.project.schedule_unit, list(self.project.roles.values_list('label', 'headcount')))
        self.assertEqual(before, after)  # 저장은 PUT /plan 이 해요
