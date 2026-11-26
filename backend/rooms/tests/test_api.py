from django.test import TestCase

from config.testing import ErdContractMixin
from projects.testing import add_to, api_as, make_project, make_user
from rooms.models import MessageAttachment, Room, RoomMessage, RoomRead
from rooms.services import room_for


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Room, set()), (RoomMessage, set()), (MessageAttachment, set()), (RoomRead, set())]


def msg(i='m1', text='안녕하세요', role='front', ts=1763431200000):
    return {'id': i, 'room': 'front', 'author': '누구든', 'role': role, 'text': text, 'time': '11:00', 'ts': ts}


class RoomTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()  # 리더 = 디자인
        self.front = add_to(self.project, 'front@example.com', 'front', name='front').user
        self.front_api, self.design_api = api_as(self.front), api_as(self.leader)

    def test_send_and_list_in_my_role_room(self):
        res = self.front_api.post('/api/rooms/front/messages', msg(), format='json')
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual((body['id'], body['room'], body['author'], body['role'], body['ts']), ('m1', 'front', 'front', 'front', 1763431200000))
        self.assertEqual([m['id'] for m in self.design_api.get('/api/rooms/front/messages').json()], ['m1'])  # 다른 역할도 읽을 수는 있어요
        self.assertEqual(RoomMessage.objects.get().checkpoint.seq, 0)  # 화면 구간이 없으면 베이스 캠프

    def test_other_role_room_is_read_only(self):
        res = self.design_api.post('/api/rooms/front/messages', msg(role='design'), format='json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()['code'], 'room_read_only')
        self.assertIn('요청 보내기', res.json()['message'])
        self.assertFalse(RoomMessage.objects.exists())

    def test_everyone_talks_in_the_all_room(self):
        self.assertEqual(self.design_api.post('/api/rooms/all/messages', msg('m1', role='design'), format='json').status_code, 201)
        self.assertEqual(self.front_api.post('/api/rooms/all/messages', msg('m2'), format='json').status_code, 201)
        self.assertEqual(len(self.front_api.get('/api/rooms/all/messages').json()), 2)
        self.assertEqual(self.front_api.get('/api/rooms/front/messages').json(), [])  # 전체 방 글은 전체 방 목록에만

    def test_only_one_all_room(self):
        room_for(self.project, 'all')
        room_for(self.project, 'all')
        self.assertEqual(Room.objects.filter(project=self.project, role__isnull=True).count(), 1)

    def test_role_is_taken_from_my_roles(self):
        res = self.front_api.post('/api/rooms/all/messages', msg(role='back'), format='json')  # 안 맡은 역할로 보내도
        self.assertEqual(res.json()['role'], 'front')

    def test_retry_is_harmless_but_ids_are_not_shared(self):
        self.front_api.post('/api/rooms/front/messages', msg(), format='json')
        self.assertEqual(self.front_api.post('/api/rooms/front/messages', msg(), format='json').status_code, 201)
        self.assertEqual(RoomMessage.objects.count(), 1)
        res = self.design_api.post('/api/rooms/all/messages', msg(role='design'), format='json')
        self.assertEqual(res.status_code, 409)

    def test_unknown_room_and_no_project(self):
        self.assertEqual(self.front_api.get('/api/rooms/qa/messages').status_code, 404)
        alone = api_as(make_user('alone@example.com'))
        self.assertEqual(alone.get('/api/rooms/all/messages').json()['code'], 'no_project')

    def test_rooms_are_per_project(self):
        self.front_api.post('/api/rooms/all/messages', msg(), format='json')
        _, boss = make_project(leader=make_user('boss@example.com'), name='다른 원정대')
        self.assertEqual(api_as(boss).get('/api/rooms/all/messages').json(), [])
