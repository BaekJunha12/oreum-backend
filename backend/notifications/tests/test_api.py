from django.test import TestCase

from config.testing import ErdContractMixin
from handoffs.tests.test_api import new_card, then
from notifications.models import Notification
from plans.models import Checkpoint
from projects.testing import add_to, api_as, make_project


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Notification, set())]


class NotificationTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()  # 리더 = 디자인
        Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        self.front = add_to(self.project, 'front@example.com', 'front', name='front').user
        self.back = add_to(self.project, 'back@example.com', 'back', name='back').user
        self.design_api, self.front_api = api_as(self.leader), api_as(self.front)
        self.card = self.front_api.post('/api/requests', new_card(), format='json').json()  # 프론트 → 디자인에게 요청

    def test_request_reaches_the_other_side_only(self):
        inbox = self.design_api.get('/api/notifications').json()
        self.assertEqual(len(inbox), 1)
        n = inbox[0]
        self.assertEqual(n['id'], 'r1:h1')
        self.assertEqual((n['cardId'], n['kind'], n['label'], n['fromRole'], n['toRole']), ('r1', 'request', '요청 받음', 'front', 'design'))
        self.assertEqual((n['actor'], n['read'], n['to']), ('front', False, '/requests/r1'))
        self.assertEqual(self.front_api.get('/api/notifications').json(), [])  # 내가 남긴 기록은 알림이 아님
        self.assertEqual(api_as(self.back).get('/api/notifications').json(), [])  # 상관없는 역할

    def test_reply_goes_back_and_delivery_links_to_review(self):
        body = then(self.card, {'type': 'deliver', 'note': 'v1'}, {'id': 'h2', 'kind': 'deliver', 'role': 'design', 'text': 'v1', 'result': 'v1'}, status='delivered')
        self.design_api.patch('/api/requests/r1', body, format='json')
        n = self.front_api.get('/api/notifications').json()[0]
        self.assertEqual((n['id'], n['label'], n['to']), ('r1:h2', '확인 필요', '/requests/r1/review'))

    def test_mark_read_only_touches_my_own(self):
        res = self.front_api.post('/api/notifications/read', {'ids': ['r1:h1']}, format='json')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Notification.objects.get().is_read)  # 디자인의 알림이라 그대로
        self.design_api.post('/api/notifications/read', {'ids': ['r1:h1', 'nope:h9']}, format='json')
        self.assertTrue(self.design_api.get('/api/notifications').json()[0]['read'])

    def test_retrying_a_card_does_not_duplicate(self):
        self.front_api.post('/api/requests', new_card(), format='json')
        self.assertEqual(Notification.objects.count(), 1)
