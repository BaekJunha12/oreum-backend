"""역할별 방 — 팀 변경 11/26: 다른 역할의 방에는 쓸 수 없고 요청보내기로 대신해요."""
from django.test import TestCase

from config.testing import ErdContractMixin
from rooms.models import MessageAttachment, Room, RoomMessage, RoomRead
from projects.testing import add_to, api_as, make_project


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(Room, set()), (RoomMessage, set()), (MessageAttachment, set()), (RoomRead, set())]


class RoomTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project(leader_role='back')
        self.designer = add_to(self.project, 'design@example.com', 'design', name='디자이너').user
        self.fronter = add_to(self.project, 'front@example.com', 'front', name='프론트').user

    def test_rooms_created_for_project(self):
        rooms = api_as(self.designer).get('/api/rooms').json()
        self.assertEqual({r['id'] for r in rooms}, {'all', 'design', 'front', 'back'})
        can = {r['id']: r['canWrite'] for r in rooms}
        self.assertEqual(can, {'all': True, 'design': True, 'front': False, 'back': False})

    def test_write_in_own_role_room(self):
        res = api_as(self.designer).post('/api/rooms/design/messages', {'id': 'm1', 'text': '시안 올렸어요'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual((res.json()['id'], res.json()['room'], res.json()['role']), ('m1', 'design', 'design'))

    def test_other_role_room_is_read_only(self):
        res = api_as(self.fronter).post('/api/rooms/design/messages', {'text': '이거 언제 돼요?'}, format='json')
        self.assertEqual((res.status_code, res.json()['code']), (403, 'room_read_only'))
        self.assertIn('요청보내기', res.json()['message'])
        # 읽기는 돼요
        self.assertEqual(api_as(self.fronter).get('/api/rooms/design/messages').status_code, 200)

    def test_all_room_open_to_everyone(self):
        res = api_as(self.fronter).post('/api/rooms/all/messages', {'text': '안녕하세요'}, format='json')
        self.assertEqual(res.status_code, 201)

    def test_leader_writes_only_in_own_role_rooms(self):
        self.assertEqual(api_as(self.leader).post('/api/rooms/back/messages', {'text': '배포했어요'}, format='json').status_code, 201)
        self.assertEqual(api_as(self.leader).post('/api/rooms/front/messages', {'text': '…'}, format='json').status_code, 403)

    def test_unread_and_read(self):
        api_as(self.designer).post('/api/rooms/all/messages', {'text': '공지'}, format='json')
        rooms = {r['id']: r for r in api_as(self.fronter).get('/api/rooms').json()}
        self.assertEqual(rooms['all']['unread'], 1)
        self.assertEqual(api_as(self.fronter).post('/api/rooms/all/read').status_code, 204)
        rooms = {r['id']: r for r in api_as(self.fronter).get('/api/rooms').json()}
        self.assertEqual(rooms['all']['unread'], 0)

    def test_handoff_attachment_links_card(self):
        api_as(self.fronter).post('/api/requests', {'id': 'r1', 'title': '로그인 시안', 'fromRole': 'design', 'toRole': 'front'}, format='json')
        res = api_as(self.designer).post('/api/rooms/design/messages', {
            'text': '시안 보냈어요', 'attachments': [{'type': 'handoff', 'strong': '로그인 시안', 'rest': '확인 부탁', 'requestId': 'r1'}],
        }, format='json')
        self.assertEqual(res.json()['attachments'][0]['requestId'], 'r1')

    def test_unknown_room_404(self):
        self.assertEqual(api_as(self.designer).get('/api/rooms/nope/messages').status_code, 404)
