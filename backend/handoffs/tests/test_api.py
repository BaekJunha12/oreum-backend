from datetime import date

from django.test import TestCase
from django.utils import timezone

from config.testing import ErdContractMixin
from handoffs.models import CardEvent, CardLink, HandoffCard
from handoffs.services import parse_when
from plans.models import Checkpoint
from projects.testing import add_to, api_as, make_project, make_user


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(HandoffCard, set()), (CardLink, set()), (CardEvent, set())]


def new_card(card_id='r1', **over):
    """프론트 createRequest() 가 만드는 모양 (받는 쪽 프론트가 디자인에게 요청)."""
    card = {
        'id': card_id, 'title': '로그인 화면', 'fromRole': 'design', 'toRole': 'front',
        'maker': '리더', 'requester': 'front', 'origin': 'request', 'links': [], 'description': '',
        'checkpoint': 1, 'due': '11/21 (금) 18:00', 'status': 'requested',
        'history': [{'id': 'h1', 'kind': 'request', 'author': 'front', 'role': 'front', 'at': '11/18 11:00', 'ts': 1763431200000, 'text': '11/21까지 로그인 화면 요청'}],
    }
    card.update(over)
    return card


def then(card, action, record, **changes):
    """프론트 change() 처럼 결과 카드를 계산해서 { action, card } 로."""
    return {'action': action, 'card': {**card, **changes, 'history': [*card['history'], record]}}


class Base(TestCase):
    def setUp(self):
        self.project, self.leader = make_project()  # 리더 = 디자인
        Checkpoint.objects.create(project=self.project, seq=1, name='로그인')
        self.front = add_to(self.project, 'front@example.com', 'front', name='front').user
        self.design_api = api_as(self.leader)
        self.front_api = api_as(self.front)

    def create(self, **over):
        res = self.front_api.post('/api/requests', new_card(**over), format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()


class CreateAndListTests(Base):
    def test_create_returns_the_same_shape(self):
        card = self.create()
        self.assertEqual(card['id'], 'r1')
        self.assertEqual((card['fromRole'], card['toRole'], card['status']), ('design', 'front', 'requested'))
        self.assertEqual((card['maker'], card['requester']), ('리더', 'front'))
        self.assertEqual(card['checkpoint'], 1)
        self.assertEqual(card['history'][0]['id'], 'h1')
        self.assertEqual(card['history'][0]['ts'], 1763431200000)

    def test_people_and_checkpoint_are_linked(self):
        self.create()
        row = HandoffCard.objects.get(pk='r1')
        self.assertEqual((row.maker_user, row.requester_user), (self.leader, self.front))
        self.assertEqual(row.checkpoint.seq, 1)
        self.assertEqual(timezone.localtime(row.due_at).strftime('%m/%d %H:%M'), '11/21 18:00')
        self.assertEqual(row.events.get().id, 'r1:h1')

    def test_unknown_checkpoint_falls_back_to_current(self):
        self.create(checkpoint=7)
        self.assertEqual(HandoffCard.objects.get(pk='r1').checkpoint.seq, 1)

    def test_every_member_sees_the_card(self):
        self.create()
        self.assertEqual([c['id'] for c in self.design_api.get('/api/requests').json()], ['r1'])

    def test_no_project_means_empty_list_and_no_create(self):
        alone = api_as(make_user('alone@example.com'))
        self.assertEqual(alone.get('/api/requests').json(), [])
        res = alone.post('/api/requests', new_card(), format='json')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['code'], 'no_project')

    def test_retry_with_same_id_is_harmless(self):
        self.create()
        res = self.front_api.post('/api/requests', new_card(), format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(HandoffCard.objects.count(), 1)

    def test_id_of_another_project_is_refused(self):
        self.create()
        other, boss = make_project(leader=make_user('boss@example.com'), name='다른 원정대')
        res = api_as(boss).post('/api/requests', new_card(), format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()['code'], 'card_id_taken')

    def test_bad_input(self):
        for bad in [new_card(card_id='r/1'), new_card(toRole='design'), new_card(history=[])]:
            with self.subTest(bad=bad['id']):
                res = self.front_api.post('/api/requests', bad, format='json')
                self.assertIn(res.status_code, (400, 409))
                self.assertIn('message', res.json())

    def test_links_are_kept_in_order(self):
        card = self.create(links=['https://figma.com/file/x', 'PR #24'])
        self.assertEqual(card['links'], ['https://figma.com/file/x', 'PR #24'])
        self.assertEqual(list(CardLink.objects.values_list('kind', flat=True)), ['figma', 'github'])


class UpdateTests(Base):
    def patch(self, client, body):
        return client.patch(f'/api/requests/{body["card"]["id"]}', body, format='json')

    def test_accept_deliver_confirm(self):
        card = self.create()
        rec = lambda i, kind, role: {'id': i, 'kind': kind, 'author': 'x', 'role': role, 'text': kind}  # noqa: E731

        card = self.patch(self.design_api, then(card, {'type': 'accept'}, rec('h2', 'accept', 'design'), status='accepted')).json()
        self.assertEqual(card['status'], 'accepted')
        card = self.patch(self.design_api, then(card, {'type': 'deliver', 'note': 'v1'}, {**rec('h3', 'deliver', 'design'), 'result': '로그인 v1'}, status='delivered')).json()
        self.assertEqual(card['history'][-1]['result'], '로그인 v1')
        card = self.patch(self.front_api, then(card, {'type': 'confirm', 'text': '좋아요'}, rec('h4', 'confirm', 'front'), status='confirmed')).json()

        self.assertEqual(card['status'], 'confirmed')
        self.assertEqual([h['kind'] for h in card['history']], ['request', 'accept', 'deliver', 'confirm'])
        self.assertIsNotNone(HandoffCard.objects.get(pk='r1').confirmed_at)

    def test_stale_action_is_a_conflict(self):
        card = self.create()
        body = then(card, {'type': 'confirm', 'text': '확인'}, {'id': 'h2', 'kind': 'confirm', 'role': 'front', 'text': '확인'}, status='confirmed')
        res = self.patch(self.front_api, body)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()['code'], 'card_conflict')
        self.assertEqual(HandoffCard.objects.get(pk='r1').status, 'requested')

    def test_result_status_must_match_the_action(self):
        card = self.create()
        res = self.patch(self.design_api, then(card, {'type': 'accept'}, {'id': 'h2', 'kind': 'accept', 'role': 'design', 'text': 'ok'}, status='confirmed'))
        self.assertEqual(res.status_code, 409)

    def test_old_records_are_never_rewritten(self):
        card = self.create()
        card['history'][0]['text'] = '바꿔치기'
        body = then(card, {'type': 'comment', 'kind': 'comment', 'text': '질문'}, {'id': 'h2', 'kind': 'comment', 'role': 'front', 'text': '질문'})
        res = self.patch(self.front_api, body).json()
        self.assertEqual(res['history'][0]['text'], '11/21까지 로그인 화면 요청')
        self.assertEqual(len(res['history']), 2)

    def test_block_and_unblock(self):
        card = self.create(status='accepted')
        card = self.patch(self.front_api, then(card, {'type': 'block', 'reason': 'API 대기'}, {'id': 'h2', 'kind': 'block', 'role': 'front', 'text': 'API 대기'}, blocked={'since': '11/19', 'reason': 'API 대기'})).json()
        self.assertEqual(card['blocked'], {'since': '11/19', 'reason': 'API 대기'})
        again = self.patch(self.front_api, then(card, {'type': 'block', 'reason': 'x'}, {'id': 'h3', 'kind': 'block', 'role': 'front', 'text': 'x'}))
        self.assertEqual(again.status_code, 409)
        card = self.patch(self.front_api, then(card, {'type': 'unblock'}, {'id': 'h3', 'kind': 'unblock', 'role': 'front', 'text': '풀림'}, blocked=None)).json()
        self.assertNotIn('blocked', card)

    def test_roles_cannot_change(self):
        card = self.create()
        body = then(card, {'type': 'accept'}, {'id': 'h2', 'kind': 'accept', 'role': 'back', 'text': 'ok'}, status='accepted', fromRole='back')
        self.assertEqual(self.patch(self.design_api, body).status_code, 403)

    def test_other_project_cannot_touch_the_card(self):
        card = self.create()
        _, boss = make_project(leader=make_user('boss@example.com'), name='다른 원정대')
        body = then(card, {'type': 'accept'}, {'id': 'h2', 'kind': 'accept', 'role': 'design', 'text': 'ok'}, status='accepted')
        self.assertEqual(self.patch(api_as(boss), body).status_code, 404)

    def test_path_and_body_must_agree(self):
        self.create()
        card = self.create(card_id='r2')
        body = then(card, {'type': 'accept'}, {'id': 'h2', 'kind': 'accept', 'role': 'design', 'text': 'ok'}, status='accepted')
        res = self.design_api.patch('/api/requests/r1', body, format='json')
        self.assertEqual(res.status_code, 409)

    def test_unknown_action(self):
        card = self.create()
        res = self.patch(self.design_api, {'action': {'type': 'delete'}, 'card': card})
        self.assertEqual(res.status_code, 400)


class ParseWhenTests(TestCase):
    def test_labels(self):
        today = date(2026, 11, 18)
        fmt = lambda t: parse_when(t, today) and timezone.localtime(parse_when(t, today)).strftime('%m/%d %H:%M')  # noqa: E731
        self.assertEqual(fmt('11/21 (금) 18:00'), '11/21 18:00')
        self.assertEqual(fmt('오늘 18:00'), '11/18 18:00')
        self.assertEqual(fmt('내일'), '11/19 00:00')
        self.assertIsNone(parse_when('체크포인트 2', today))
        self.assertIsNone(parse_when('13/40', today))
