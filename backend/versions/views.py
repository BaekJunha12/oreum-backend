"""GitHub 진행 단계 · 버전 비교 · 진행 상태 탭 API (팀 변경 11/26 "버전 비교/상태 탭").

    GET    /api/github                        연결한 저장소 + 단계별 PR
    POST   /api/github/repos                  저장소 연결 { owner, name, installationId? }  (리더)
    DELETE /api/github/repos/<id>             연결 끊기 (리더)
    GET    /api/github/pulls                  PR 목록 (?stage=work|review|merged|deployed)
    POST   /api/github/pulls                  PR 만들기 · 고치기 { repo?, number, title, url, headBranch, baseBranch, author, stage?, cards? }
    PATCH  /api/github/pulls/<id>             단계 · 연결 카드 바꾸기 { stage?, cards? }  — deployed 면 연결 카드 자동 전달
    POST   /api/github/webhook                GitHub 웹훅 (GITHUB_WEBHOOK_SECRET 이 있을 때만)

    GET    /api/versions                      배포 기록 (?environment=prod|dev)
    POST   /api/versions                      배포 기록 남기기 { environment, versionLabel, siteUrl, branch?, sourcePr?, deployedAt? }
    GET    /api/versions/compare              두 버전 비교 (?base=&head=, 생략하면 최신 prod ↔ 최신 dev) + 화면별 코멘트 + 달라진 PR
    GET    /api/versions/<id>/comments        코멘트 (?screen=메인 피드 · ?open=1 해결 안 된 것만)
    POST   /api/versions/<id>/comments        코멘트 · 핀 { screen, body, x?, y?, kind?, parent?, role? }
    PATCH  /api/compare-comments/<id>         { body?, resolved? }
    DELETE /api/compare-comments/<id>         지우기 (쓴 사람 · 리더)
    POST   /api/compare-comments/<id>/request 코멘트 → 요청 카드 { fromRole, title?, due?, toRole? }

    GET    /api/status                        진행 상태 탭 한 번에: 남은 시간 · 구간 · 단계별 PR · 요청 수 · 열린 코멘트 · 최신 버전
"""
import json

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from handoffs.payloads import card_payload
from handoffs.services import card_for
from projects.services import project_context

from . import services
from .models import AppVersion, CompareComment, GithubPullRequest
from .payloads import comment_payload, pull_payload, repo_payload, screens_payload, status_payload, version_payload

STAGES = [s for s, _ in GithubPullRequest.STAGES]


class RepoInput(serializers.Serializer):
    owner = serializers.RegexField(r'^[A-Za-z0-9-]{1,100}$')
    name = serializers.RegexField(r'^[A-Za-z0-9._-]{1,100}$')
    installationId = serializers.CharField(max_length=50, required=False, allow_blank=True)


class PullInput(serializers.Serializer):
    repo = serializers.CharField(max_length=210, required=False, allow_blank=True)
    number = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=255, required=False)
    url = serializers.URLField(max_length=500, required=False)
    headBranch = serializers.CharField(max_length=255, required=False)
    baseBranch = serializers.CharField(max_length=255, required=False)
    author = serializers.CharField(max_length=100, required=False, allow_blank=True)
    stage = serializers.ChoiceField(STAGES, required=False)
    cards = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=50)

    def to_service(self):
        d = self.validated_data
        return {
            'repo': d.get('repo'), 'number': d['number'], 'title': d.get('title'), 'url': d.get('url'),
            'head_branch': d.get('headBranch'), 'base_branch': d.get('baseBranch'), 'author_login': d.get('author') or None,
            'stage': d.get('stage'), 'cards': d.get('cards'),
        }


class PullUpdateInput(serializers.Serializer):
    stage = serializers.ChoiceField(STAGES, required=False)
    cards = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=50)


class VersionInput(serializers.Serializer):
    environment = serializers.ChoiceField([e for e, _ in AppVersion.ENVIRONMENTS])
    versionLabel = serializers.CharField(max_length=50)
    siteUrl = serializers.URLField(max_length=700)
    branch = serializers.CharField(max_length=100, required=False, allow_blank=True)
    sourcePr = serializers.IntegerField(required=False, allow_null=True)
    deployedAt = serializers.DateTimeField(required=False)


class CommentInput(serializers.Serializer):
    screen = serializers.CharField(max_length=100, required=False)
    body = serializers.CharField(max_length=5000)
    x = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    y = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    kind = serializers.ChoiceField([k for k, _ in CompareComment.KINDS], required=False)
    parent = serializers.IntegerField(required=False, allow_null=True)
    role = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, data):
        if not data.get('parent') and not (data.get('screen') or '').strip():
            raise serializers.ValidationError({'screen': '어느 화면인지 적어 주세요'})
        return data


class CommentUpdateInput(serializers.Serializer):
    body = serializers.CharField(max_length=5000, required=False)
    resolved = serializers.BooleanField(required=False)


class CommentRequestInput(serializers.Serializer):
    id = serializers.CharField(max_length=64, required=False)
    fromRole = serializers.CharField(max_length=64)
    toRole = serializers.CharField(max_length=64, required=False)
    title = serializers.CharField(max_length=255, required=False)
    due = serializers.CharField(max_length=50, required=False, allow_blank=True)
    checkpoint = serializers.IntegerField(required=False, allow_null=True, min_value=0)


def _valid(serializer_class, request, partial=False):
    s = serializer_class(data=request.data, partial=partial)
    s.is_valid(raise_exception=True)
    return s


# ───────── GitHub ─────────

class Github(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        if project is None:
            return Response({'repos': [], 'pulls': {s: [] for s in STAGES}})
        pulls = list(services.pulls_of(project))
        return Response({
            'repos': [repo_payload(r) for r in services.repos_of(project)],
            'pulls': {s: [pull_payload(p) for p in pulls if p.stage == s] for s in STAGES},
        })


class Repos(APIView):
    def post(self, request):
        d = _valid(RepoInput, request).validated_data
        project, _ = project_context(request)
        repo = services.connect_repo(request.user, project, owner=d['owner'], name=d['name'], installation_id=d.get('installationId'))
        return Response(repo_payload(repo), status=status.HTTP_201_CREATED)


class RepoDetail(APIView):
    def delete(self, request, repo_id):
        project, _ = project_context(request)
        services.disconnect_repo(request.user, services.repo_for(project, repo_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class Pulls(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        if project is None:
            return Response([])
        stage = request.query_params.get('stage')
        return Response([pull_payload(p) for p in services.pulls_of(project, stage if stage in STAGES else None)])

    def post(self, request):
        s = _valid(PullInput, request)
        project, _ = project_context(request)
        pr = services.save_pull(request.user, project, s.to_service())
        return Response(pull_payload(services.pull_for(project, pr.pk)), status=status.HTTP_201_CREATED)


class PullDetail(APIView):
    def get(self, request, pr_id):
        project, _ = project_context(request)
        return Response(pull_payload(services.pull_for(project, pr_id)))

    def patch(self, request, pr_id):
        d = _valid(PullUpdateInput, request).validated_data
        project, _ = project_context(request)
        pr = services.pull_for(project, pr_id)
        services.save_pull(request.user, project, {'repo': pr.repo, 'number': pr.number, 'stage': d.get('stage'), 'cards': d.get('cards')})
        return Response(pull_payload(services.pull_for(project, pr_id)))


class GithubWebhook(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        body = request.body
        services.check_signature(body, request.headers.get('X-Hub-Signature-256'))
        try:
            payload = json.loads(body or b'{}')
        except ValueError:
            return Response({'message': 'JSON 이 아니에요', 'code': 'bad_json'}, status=status.HTTP_400_BAD_REQUEST)
        updated = services.handle_webhook(request.headers.get('X-GitHub-Event', ''), payload)
        return Response({'updated': updated})


# ───────── 배포 기록 · 비교 ─────────

class Versions(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        if project is None:
            return Response([])
        env = request.query_params.get('environment')
        return Response([version_payload(v) for v in services.versions_of(project, env if env in ('prod', 'dev') else None)])

    def post(self, request):
        d = _valid(VersionInput, request).validated_data
        project, _ = project_context(request)
        version = services.add_version(request.user, project, {
            'environment': d['environment'], 'version_label': d['versionLabel'], 'site_url': d['siteUrl'],
            'branch': d.get('branch'), 'source_pr': d.get('sourcePr'), 'deployed_at': d.get('deployedAt'),
        })
        return Response(version_payload(services.version_for(project, version.pk)), status=status.HTTP_201_CREATED)


def _int(value):
    return int(value) if str(value or '').isdigit() else None


class Compare(APIView):
    def get(self, request):
        project, _ = project_context(request)
        q = request.query_params
        base, head = services.compare_pair(project, _int(q.get('base')), _int(q.get('head')))
        return Response({
            'base': {**version_payload(base), 'screens': screens_payload(services.comments_of(base))},
            'head': {**version_payload(head), 'screens': screens_payload(services.comments_of(head))},
            'pulls': [pull_payload(p) for p in services.pulls_between(project, base, head)],
        })


class VersionComments(APIView):
    def get(self, request, version_id):
        project, _ = project_context(request)
        version = services.version_for(project, version_id)
        q = request.query_params
        rows = services.comments_of(version, q.get('screen'), include_resolved=q.get('open') != '1').filter(parent__isnull=True)
        return Response([comment_payload(c) for c in rows])

    def post(self, request, version_id):
        d = _valid(CommentInput, request).validated_data
        project, _ = project_context(request)
        comment = services.add_comment(request.user, services.version_for(project, version_id), d)
        return Response(comment_payload(services.comment_for(project, comment.pk)), status=status.HTTP_201_CREATED)


class CommentDetail(APIView):
    def patch(self, request, comment_id):
        d = _valid(CommentUpdateInput, request).validated_data
        project, _ = project_context(request)
        comment = services.update_comment(request.user, services.comment_for(project, comment_id), d)
        return Response(comment_payload(services.comment_for(project, comment.pk)))

    def delete(self, request, comment_id):
        project, _ = project_context(request)
        services.delete_comment(request.user, services.comment_for(project, comment_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentRequest(APIView):
    def post(self, request, comment_id):
        d = _valid(CommentRequestInput, request).validated_data
        project, _ = project_context(request)
        card = services.comment_to_request(request.user, services.comment_for(project, comment_id), d)
        return Response(card_payload(card_for(request.user, project, card.pk)), status=status.HTTP_201_CREATED)


# ───────── 진행 상태 탭 ─────────

class Status(APIView):
    def get(self, request):
        project, _ = project_context(request)
        return Response(status_payload(services.status_summary(project), project, request.user))
