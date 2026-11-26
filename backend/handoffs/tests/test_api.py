"""요청 카드 API (요청보내기) — 서버가 상태표를 직접 지켜요."""
from django.test import TestCase, override_settings

from config.testing import ErdContractMixin
from handoffs.models import CardEvent, CardLink, HandoffCard
from projects.testing import add_to, api_as, make_project


def card_body(**over):
    body = {'id': 'r-login', 'title': '로그인 시안', 'fromRole': 'design', 'toRole': 'front', 'due': '11/28 (금)', 'checkpoint': 1,
            'history': [{'id': 'h-1', 'kind': 'request', 'text': '금요일까지 로그인 시안 부탁해요'}]}
    body.update(over)
    return body


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(HandoffCard, set()), (CardLink, set()), (CardEvent, set())]


class CardFlowTests(TestCase):
    def setUp(self):
        self.project, self.leader = make_project(leader_role='back')
        self.designer = add_to(self.project, 'design@example.com', 'design', name='디자이너').user
        self.fronter = add_to(self.project, 'front@example.com', 'front', name='프론트').user
        self.design_api, self.front_api = api_as(self.designer), api_as(self.fronter)

    def create(self, **over):
        res = self.front_api.post('/api/requests', card_body(**over), format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def act(self, api, card_id, **action):
        return api.patch(f'/api/requests/{card_id}', {'action': action}, format='json')

    def test_create_keeps_client_ids_and_sets_requester(self):
        card = self.create()
        self.assertEqual(card['id'], 'r-login')
        self.assertEqual(card['status'], 'requested')
        self.assertEqual(card['requester'], '프론트')
        self.assertEqual(card['history'][0]['id'], 'h-1')

    def test_full_flow_request_accept_deliver_confirm(self):
        self.create()
        self.assertEqual(self.act(self.design_api, 'r-login', type='accept').json()['status'], 'accepted')
        res = self.act(self.design_api, 'r-login', type='deliver', note='확인 부탁', link='https://figma.com/file/abc')
        self.assertEqual(res.json()['status'], 'delivered')
        self.assertIn('https://figma.com/file/abc', res.json()['links'])
        res = self.act(self.front_api, 'r-login', type='confirm', text='좋아요')
        self.assertEqual(res.json()['status'], 'confirmed')
        kinds = [h['kind'] for h in res.json()['history']]
        self.assertEqual(kinds, ['request', 'accept', 'deliver', 'confirm'])

    def test_requester_cannot_accept(self):
        self.create()
        res = self.act(self.front_api, 'r-login', type='accept')
        self.assertEqual((res.status_code, res.json()['code']), (403, 'maker_only'))

    def test_maker_cannot_confirm(self):
        self.create()
        self.act(self.design_api, 'r-login', type='deliver', note='')
        self.assertEqual(self.act(self.design_api, 'r-login', type='confirm').status_code, 403)

    def test_invalid_transition_is_409(self):
        self.create()
        res = self.act(self.front_api, 'r-login', type='confirm')
        self.assertEqual((res.status_code, res.json()['code']), (409, 'invalid_transition'))

    def test_propose_then_accept_proposed(self):
        self.create()
        self.act(self.design_api, 'r-login', type='propose', date='12/01 (월)')
        res = self.act(self.front_api, 'r-login', type='acceptProposed')
        self.assertEqual((res.json()['status'], res.json()['due']), ('accepted', '12/01 (월)'))

    def test_fix_sends_back_to_accepted_and_redeliver(self):
        self.create()
        self.act(self.design_api, 'r-login', type='deliver', note='v1')
        self.assertEqual(self.act(self.front_api, 'r-login', type='fix', text='버튼 색').json()['status'], 'accepted')
        res = self.act(self.design_api, 'r-login', type='deliver', note='v2')
        self.assertEqual(res.json()['history'][-1]['kind'], 'redeliver')

    def test_block_and_unblock(self):
        self.create()
        self.act(self.design_api, 'r-login', type='accept')
        res = self.act(self.front_api, 'r-login', type='block', reason='시안 기다리는 중')
        self.assertEqual(res.json()['blocked']['reason'], '시안 기다리는 중')
        self.assertNotIn('blocked', self.act(self.front_api, 'r-login', type='unblock').json())

    def test_anyone_can_comment(self):
        self.create()
        back = add_to(self.project, 'back@example.com', 'back').user
        res = self.act(api_as(back), 'r-login', type='comment', text='API 는 준비됐어요')
        self.assertEqual(res.status_code, 200, res.content)

    def test_handoff_merges_into_waiting_card(self):
        self.create()
        res = self.design_api.post('/api/requests', card_body(id='r-new', origin='handoff', links=['시안 v1'], history=[]), format='json')
        self.assertEqual(res.status_code, 200)  # 새로 만들지 않고 기다리던 카드를 전달
        self.assertEqual(res.json()['id'], 'r-login')
        self.assertEqual(res.json()['status'], 'delivered')

    def test_duplicate_id_conflict(self):
        self.create()
        res = self.front_api.post('/api/requests', card_body(title='다른 것'), format='json')
        self.assertEqual(res.status_code, 409)

    def test_filters(self):
        self.create()
        self.create(id='r-feed', title='피드 시안')
        self.act(self.design_api, 'r-feed', type='accept')
        self.assertEqual([c['id'] for c in self.front_api.get('/api/requests?status=accepted').json()], ['r-feed'])
        self.assertEqual(len(self.front_api.get('/api/requests?role=design').json()), 2)

    def test_outsider_gets_404(self):
        self.create()
        other_project, other = make_project(add_to(self.project, 'x@example.com').user, name='다른 원정대')
        res = api_as(other).get('/api/requests/r-login', HTTP_X_PROJECT_ID=str(other_project.pk))
        self.assertEqual(res.status_code, 404)

    @override_settings(DEBUG=True)
    def test_reset_demo_seeds_cards(self):
        res = api_as(self.leader).post('/api/requests/reset')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json())
        self.assertTrue(all(c['id'].startswith(f'p{self.project.pk}-') for c in res.json()))
