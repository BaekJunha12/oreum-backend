"""GitHub 진행 단계 · 버전 비교 · 진행 상태 탭 (팀 변경 11/26)."""
import hashlib
import hmac
import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from config.testing import ErdContractMixin
from handoffs.models import HandoffCard
from notifications.models import Notification
from projects.testing import add_to, api_as, make_project
from versions.models import AppVersion, CompareComment, GithubPullRequest, GithubRepository


class SchemaContractTests(ErdContractMixin, TestCase):
    models = [(GithubRepository, set()), (GithubPullRequest, set()), (AppVersion, set()), (CompareComment, set())]


class Base(TestCase):
    def setUp(self):
        self.project, self.leader = make_project(leader_role='back')
        self.designer = add_to(self.project, 'design@example.com', 'design', name='디자이너').user
        self.fronter = add_to(self.project, 'front@example.com', 'front', name='프론트').user
        self.lead_api, self.front_api, self.design_api = api_as(self.leader), api_as(self.fronter), api_as(self.designer)

    def connect(self):
        res = self.lead_api.post('/api/github/repos', {'owner': 'oreum-team', 'name': 'campus-app'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def pull(self, api=None, **over):
        body = {'number': 24, 'title': '로그인 화면', 'url': 'https://github.com/oreum-team/campus-app/pull/24',
                'headBranch': 'feat/login', 'baseBranch': 'main', 'author': 'front-dev'}
        body.update(over)
        res = (api or self.front_api).post('/api/github/pulls', body, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()


class RepoTests(Base):
    def test_leader_connects_repo(self):
        repo = self.connect()
        self.assertEqual(repo['fullName'], 'oreum-team/campus-app')
        self.assertEqual(self.front_api.get('/api/github').json()['repos'][0]['name'], 'campus-app')

    def test_member_cannot_connect(self):
        res = self.front_api.post('/api/github/repos', {'owner': 'x', 'name': 'y'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_duplicate_repo(self):
        self.connect()
        res = self.lead_api.post('/api/github/repos', {'owner': 'oreum-team', 'name': 'campus-app'}, format='json')
        self.assertEqual((res.status_code, res.json()['code']), (409, 'repo_exists'))


class PullStageTests(Base):
    def setUp(self):
        super().setUp()
        self.connect()
        self.front_api.post('/api/requests', {'id': 'r-api', 'title': '로그인 API', 'fromRole': 'back', 'toRole': 'front'}, format='json')

    def test_upsert_by_number(self):
        first = self.pull()
        again = self.pull(title='로그인 화면 (수정)', stage='review')
        self.assertEqual(first['id'], again['id'])
        self.assertEqual((again['title'], again['stage'], again['stageLabel']), ('로그인 화면 (수정)', 'review', '리뷰'))

    def test_stages_grouped(self):
        self.pull()
        self.pull(number=25, title='피드', url='https://github.com/oreum-team/campus-app/pull/25', stage='merged')
        pulls = self.front_api.get('/api/github').json()['pulls']
        self.assertEqual(([p['number'] for p in pulls['work']], [p['number'] for p in pulls['merged']]), ([24], [25]))
        self.assertIsNotNone(pulls['merged'][0]['mergedAt'])

    def test_deploy_auto_delivers_linked_cards(self):
        pr = self.pull(api=self.lead_api, cards=['r-api'])
        res = self.lead_api.patch(f"/api/github/pulls/{pr['id']}", {'stage': 'deployed'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        card = HandoffCard.objects.get(pk='r-api')
        self.assertEqual((card.status, card.is_auto), ('delivered', True))
        last = card.events.order_by('-created_at').first()
        self.assertIn('PR #24 배포로 자동 전달', last.text)
        # 요청한 쪽(프론트)에 '확인 필요' 알림
        self.assertTrue(Notification.objects.filter(user=self.fronter, event=last).exists())
        detail = self.front_api.get('/api/requests/r-api').json()
        self.assertEqual(detail['status'], 'delivered')

    def test_only_leader_moves_backwards(self):
        pr = self.pull(stage='merged')
        res = self.front_api.patch(f"/api/github/pulls/{pr['id']}", {'stage': 'work'}, format='json')
        self.assertEqual((res.status_code, res.json()['code']), (403, 'leader_only'))
        self.assertEqual(self.lead_api.patch(f"/api/github/pulls/{pr['id']}", {'stage': 'work'}, format='json').json()['stage'], 'work')

    def test_unknown_card_404(self):
        res = self.front_api.post('/api/github/pulls', {'number': 30, 'title': 't', 'url': 'https://github.com/a/b/pull/30', 'cards': ['nope']}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_pr_attachment_follows_stage(self):
        self.pull(stage='review')
        res = self.front_api.post('/api/rooms/front/messages', {
            'text': 'PR 올렸어요', 'attachments': [{'type': 'pr', 'title': '#24 로그인 화면', 'branch': 'feat/login', 'badge': {'tone': 'auto'}}],
        }, format='json')
        stages = [s['state'] for s in res.json()['attachments'][0]['stages']]
        self.assertEqual(stages, ['done', 'done', 'current', 'todo'])


SECRET = 'test-secret'


@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
class WebhookTests(Base):
    def send(self, payload, event='pull_request', secret=SECRET):
        body = json.dumps(payload).encode()
        sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post('/api/github/webhook', body, content_type='application/json',
                                headers={'X-GitHub-Event': event, 'X-Hub-Signature-256': sig})

    def payload(self, action, merged=False):
        return {'action': action, 'number': 24, 'repository': {'name': 'campus-app', 'owner': {'login': 'oreum-team'}},
                'pull_request': {'number': 24, 'title': '로그인', 'html_url': 'https://github.com/oreum-team/campus-app/pull/24',
                                 'merged': merged, 'head': {'ref': 'feat/login'}, 'base': {'ref': 'main'}, 'user': {'login': 'dev'}}}

    def test_opened_then_merged(self):
        self.connect()
        self.assertEqual(self.send(self.payload('opened')).json(), {'updated': 1})
        self.send(self.payload('closed', merged=True))
        pr = GithubPullRequest.objects.get()
        self.assertEqual(pr.stage, 'merged')
        self.assertIsNotNone(pr.merged_at)

    def test_bad_signature(self):
        self.connect()
        self.assertEqual(self.send(self.payload('opened'), secret='wrong').status_code, 403)

    def test_unknown_repo_ignored(self):
        self.assertEqual(self.send(self.payload('opened')).json(), {'updated': 0})

    @override_settings(GITHUB_WEBHOOK_SECRET='')
    def test_disabled_without_secret(self):
        self.assertEqual(self.send(self.payload('opened')).status_code, 404)


class CompareTests(Base):
    def setUp(self):
        super().setUp()
        self.connect()
        now = timezone.now()
        self.prod = self.front_api.post('/api/versions', {'environment': 'prod', 'versionLabel': 'v1.2.0', 'siteUrl': 'https://campus.example',
                                                          'deployedAt': (now - timedelta(days=3)).isoformat()}, format='json').json()
        self.pr = self.pull(stage='merged')
        self.dev = self.front_api.post('/api/versions', {'environment': 'dev', 'versionLabel': 'v1.3.0-dev', 'siteUrl': 'https://dev.campus.example',
                                                         'branch': 'dev'}, format='json').json()

    def test_default_compare_is_prod_vs_dev(self):
        res = self.design_api.get('/api/versions/compare')
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual((body['base']['versionLabel'], body['head']['versionLabel']), ('v1.2.0', 'v1.3.0-dev'))
        self.assertEqual([p['number'] for p in body['pulls']], [24])  # prod 뒤에 병합된 PR

    def test_comments_grouped_by_screen_with_replies(self):
        c = self.design_api.post(f"/api/versions/{self.dev['id']}/comments", {'screen': '메인 피드', 'body': '여백이 좁아요', 'x': 120, 'y': 340}, format='json')
        self.assertEqual(c.status_code, 201, c.content)
        self.assertEqual((c.json()['role'], c.json()['pin']), ('design', {'x': 120, 'y': 340}))
        self.front_api.post(f"/api/versions/{self.dev['id']}/comments", {'parent': int(c.json()['id']), 'body': '고칠게요'}, format='json')
        screens = self.design_api.get('/api/versions/compare').json()['head']['screens']
        self.assertEqual(screens[0]['screen'], '메인 피드')
        self.assertEqual(screens[0]['open'], 1)
        self.assertEqual(screens[0]['comments'][0]['replies'][0]['body'], '고칠게요')

    def test_resolve_and_open_filter(self):
        c = self.design_api.post(f"/api/versions/{self.dev['id']}/comments", {'screen': '로그인', 'body': '버튼'}, format='json').json()
        res = self.front_api.patch(f"/api/compare-comments/{c['id']}", {'resolved': True}, format='json')
        self.assertEqual((res.json()['resolved'], res.json()['resolvedBy']), (True, '프론트'))
        self.assertEqual(self.front_api.get(f"/api/versions/{self.dev['id']}/comments?open=1").json(), [])

    def test_only_author_edits_body(self):
        c = self.design_api.post(f"/api/versions/{self.dev['id']}/comments", {'screen': '로그인', 'body': '버튼'}, format='json').json()
        self.assertEqual(self.front_api.patch(f"/api/compare-comments/{c['id']}", {'body': '바꿈'}, format='json').status_code, 403)

    def test_comment_needs_screen(self):
        res = self.design_api.post(f"/api/versions/{self.dev['id']}/comments", {'body': '어디?'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_comment_to_request_card(self):
        c = self.design_api.post(f"/api/versions/{self.dev['id']}/comments", {'screen': '메인 피드', 'body': '카드 그림자 빠짐'}, format='json').json()
        res = self.design_api.post(f"/api/compare-comments/{c['id']}/request", {'fromRole': 'front', 'due': '11/28'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        card = res.json()
        self.assertEqual((card['fromRole'], card['toRole'], card['status'], card['tag']), ('front', 'design', 'requested', '버전 비교'))
        self.assertIn('카드 그림자 빠짐', card['description'])
        self.assertEqual(CompareComment.objects.get(pk=c['id']).card_id, card['id'])
        again = self.design_api.post(f"/api/compare-comments/{c['id']}/request", {'fromRole': 'front'}, format='json')
        self.assertEqual(again.status_code, 409)

    def test_prod_version_with_pr_marks_deployed(self):
        res = self.lead_api.post('/api/versions', {'environment': 'prod', 'versionLabel': 'v1.3.0', 'siteUrl': 'https://campus.example',
                                                  'sourcePr': int(self.pr['id'])}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(GithubPullRequest.objects.get(pk=self.pr['id']).stage, 'deployed')

    def test_compare_without_versions(self):
        other, leader = make_project(add_to(self.project, 'solo@example.com').user, name='빈 원정대')
        res = api_as(leader).get('/api/versions/compare', HTTP_X_PROJECT_ID=str(other.pk))
        self.assertEqual((res.status_code, res.json()['code']), (404, 'versions_missing'))


class StatusTabTests(Base):
    def test_status_summary(self):
        self.connect()
        self.pull(stage='review')
        self.front_api.post('/api/requests', {'id': 'r1', 'title': '시안', 'fromRole': 'design', 'toRole': 'front'}, format='json')
        res = self.design_api.get('/api/status')
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body['pullCounts'], {'work': 0, 'review': 1, 'merged': 0, 'deployed': 0})
        self.assertEqual(body['requests']['requested'], 1)
        self.assertIn('남음', body['remaining']['text'])
        self.assertEqual(body['versions'], {'prod': None, 'dev': None})
