"""알림 — 카드 기록이 생기면 반대쪽 역할에게 한 줄씩."""
from django.test import TestCase

from config.testing import ErdContractMixin
from notifications.models import Notification
from projects.testing import add_to, api_as, make_project


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Notification, set())]


class NotificationTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project(leader_role='back')
        self.designer = add_to(self.project, 'design@example.com', 'design', name='디자이너').user
        self.fronter = add_to(self.project, 'front@example.com', 'front', name='프론트').user
        api_as(self.fronter).post('/api/requests', {
            'id': 'r1', 'title': '로그인 시안', 'fromRole': 'design', 'toRole': 'front', 'due': '11/28',
            'history': [{'id': 'h1', 'kind': 'request', 'text': '부탁해요'}],
        }, format='json')

    def test_request_notifies_maker_side_only(self):
        mine = api_as(self.designer).get('/api/notifications').json()
        self.assertEqual([n['id'] for n in mine], ['r1:h1'])
        self.assertEqual(api_as(self.fronter).get('/api/notifications').json(), [])  # 내가 한 일은 알림이 아니에요

    def test_deliver_notifies_requester(self):
        api_as(self.designer).patch('/api/requests/r1', {'action': {'type': 'deliver', 'note': 'v1'}}, format='json')
        self.assertEqual(api_as(self.fronter).get('/api/notifications/unread-count').json()['count'], 1)

    def test_mark_read_with_frontend_ids(self):
        api = api_as(self.designer)
        self.assertEqual(api.post('/api/notifications/read', {'ids': ['r1:h1']}, format='json').status_code, 204)
        self.assertEqual(api.get('/api/notifications/unread-count').json()['count'], 0)
        self.assertTrue(Notification.objects.get(user=self.designer).is_read)

    def test_mark_all_read(self):
        api = api_as(self.designer)
        api.post('/api/notifications/read', {}, format='json')
        self.assertEqual(api.get('/api/notifications?unread=1').json(), [])
