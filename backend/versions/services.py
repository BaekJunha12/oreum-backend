"""GitHub 진행 단계 · 버전 비교 규칙.

PR 단계 (앞으로만 가요, 되돌릴 때는 리더만):
    work(작업) → review(리뷰) → merged(병합) → deployed(배포)
    배포가 되면 PR 에 연결한 요청 카드 중 아직 안 끝난 것(요청됨 · 진행 중)을 서버가 '전달됨'으로 바꿔요.
    카드에는 is_auto = true, 기록에는 'PR #24 배포로 자동 전달' 이 남고, 요청한 쪽에 '확인 필요' 알림이 가요.

GitHub 웹훅 (POST /api/github/webhook) — GITHUB_WEBHOOK_SECRET 을 넣었을 때만 켜져요.
    pull_request opened · reopened · synchronize        → work
    pull_request ready_for_review · review_requested    → review
    pull_request closed + merged                         → merged
    배포는 GitHub 이 알려 주지 않아서 POST /api/versions 로 배포 기록을 남길 때 sourcePr 를 같이 보내면 deployed 가 돼요.
"""
import hashlib
import hmac

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from handoffs import services as cards
from handoffs.models import HandoffCard
from projects.errors import Conflict, Forbidden, NotFound
from projects.services import is_leader, match_role, membership, require_leader, roles_of

from .models import AppVersion, CompareComment, GithubPullRequest, GithubRepository

STAGE_INDEX = {s: i for i, s in enumerate(GithubPullRequest.ORDER)}


def require_member(user, project):
    m = membership(user, project)
    if m is None:
        raise Forbidden('원정대원만 할 수 있어요')
    return m


# ───────── 저장소 ─────────

def repos_of(project):
    return GithubRepository.objects.filter(project=project)


def connect_repo(user, project, *, owner, name, installation_id=None):
    require_leader(user, project)
    try:
        with transaction.atomic():
            return GithubRepository.objects.create(
                project=project, owner=owner.strip(), name=name.strip(), installation_id=installation_id or None, connected_by=user,
            )
    except IntegrityError:
        raise Conflict('이미 연결한 저장소예요', code='repo_exists')


def repo_for(project, ref):
    """ref = 저장소 id 또는 'owner/name'."""
    qs = repos_of(project)
    ref = str(ref or '').strip()
    repo = qs.filter(pk=int(ref)).first() if ref.isdigit() else None
    if repo is None and '/' in ref:
        owner, name = ref.split('/', 1)
        repo = qs.filter(owner__iexact=owner, name__iexact=name).first()
    if repo is None and not ref and qs.count() == 1:
        repo = qs.first()  # 저장소가 하나뿐이면 생략해도 돼요
    if repo is None:
        raise NotFound('연결한 저장소를 찾을 수 없어요', code='repo_not_found')
    return repo


def disconnect_repo(user, repo):
    require_leader(user, repo.project)
    repo.delete()


# ───────── PR ─────────

def pulls_of(project, stage=None):
    qs = GithubPullRequest.objects.filter(repo__project=project).select_related('repo').prefetch_related('cards')
    return qs.filter(stage=stage) if stage else qs


def pull_for(project, pr_id):
    pr = pulls_of(project).filter(pk=pr_id).first()
    if pr is None:
        raise NotFound('PR 을 찾을 수 없어요', code='pr_not_found')
    return pr


def _link_cards(pr, card_ids):
    if card_ids is None:
        return
    found = list(HandoffCard.objects.filter(project=pr.repo.project, pk__in=card_ids))
    if len(found) != len(set(card_ids)):
        raise NotFound('연결할 요청을 찾을 수 없어요', code='card_not_found')
    HandoffCard.objects.filter(github_pr=pr).exclude(pk__in=card_ids).update(github_pr=None)
    HandoffCard.objects.filter(pk__in=card_ids).update(github_pr=pr)


@transaction.atomic
def save_pull(user, project, data, *, by_webhook=False):
    """PR 하나를 만들거나 고쳐요 (저장소 + 번호가 같으면 같은 PR)."""
    if not by_webhook:
        require_member(user, project)
    repo = data['repo'] if isinstance(data.get('repo'), GithubRepository) else repo_for(project, data.get('repo'))
    pr = GithubPullRequest.objects.select_for_update().filter(repo=repo, number=data['number']).first()
    fields = {k: data[k] for k in ('title', 'head_branch', 'base_branch', 'author_login', 'url') if data.get(k) is not None}
    if pr is None:
        missing = [k for k in ('title', 'url') if not fields.get(k)]
        if missing:
            raise Conflict('새 PR 은 제목과 주소가 있어야 해요', code='pr_fields_required')
        fields.setdefault('head_branch', '')
        fields.setdefault('base_branch', 'main')
        pr = GithubPullRequest.objects.create(repo=repo, number=data['number'], **fields)
    else:
        for k, v in fields.items():
            setattr(pr, k, v)
        pr.save()
    _link_cards(pr, data.get('cards'))
    if data.get('stage'):
        move_stage(user, pr, data['stage'], by_webhook=by_webhook)
    return pr


def move_stage(user, pr, stage, *, by_webhook=False, when=None):
    """단계 바꾸기. 뒤로 가는 건 리더만 (웹훅은 GitHub 이 알려 준 그대로)."""
    if stage not in STAGE_INDEX:
        raise Conflict('모르는 단계예요', code='invalid_stage')
    project = pr.repo.project
    if not by_webhook and STAGE_INDEX[stage] < STAGE_INDEX[pr.stage] and not is_leader(user, project):
        raise Forbidden('이전 단계로 되돌리는 건 리더만 할 수 있어요', code='leader_only')
    if stage == pr.stage:
        return pr
    when = when or timezone.now()
    pr.stage = stage
    if STAGE_INDEX[stage] >= STAGE_INDEX[GithubPullRequest.MERGED] and pr.merged_at is None:
        pr.merged_at = when
    if stage == GithubPullRequest.DEPLOYED:
        pr.deployed_at = pr.deployed_at or when
    if STAGE_INDEX[stage] < STAGE_INDEX[GithubPullRequest.MERGED]:
        pr.merged_at = None
    if stage != GithubPullRequest.DEPLOYED:
        pr.deployed_at = None
    pr.save()
    if stage == GithubPullRequest.DEPLOYED:
        auto_deliver(user or project.created_by, pr)
    return pr


def auto_deliver(user, pr):
    """배포된 PR 에 연결한 열린 카드 → 전달됨 (is_auto) + 기록 + 알림. 돌려주는 값 = 바뀐 카드 수."""
    moved = 0
    for card in HandoffCard.objects.select_for_update().filter(github_pr=pr, status__in=[HandoffCard.REQUESTED, HandoffCard.ACCEPTED]):
        card.status = HandoffCard.DELIVERED
        card.is_auto = True
        card.blocked_since = card.blocked_reason = None
        card.proposed_due_at = card.proposed_due_label = None
        card.save(update_fields=['status', 'is_auto', 'blocked_since', 'blocked_reason', 'proposed_due_at', 'proposed_due_label', 'updated_at'])
        result = f'PR #{pr.number}'
        cards.add_event(card, user, 'deliver', f'{result} 배포로 자동 전달 · 확인 부탁', role=card.from_role,
                        result_title=result, result_url=pr.url)
        moved += 1
    return moved


# ───────── 웹훅 ─────────

WEBHOOK_STAGE = {
    'opened': GithubPullRequest.WORK, 'reopened': GithubPullRequest.WORK, 'synchronize': None, 'edited': None,
    'ready_for_review': GithubPullRequest.REVIEW, 'review_requested': GithubPullRequest.REVIEW, 'converted_to_draft': GithubPullRequest.WORK,
}


def check_signature(body, header):
    secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')
    if not secret:
        raise NotFound('GitHub 웹훅이 꺼져 있어요', code='webhook_disabled')
    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, header or ''):
        raise Forbidden('서명이 맞지 않아요', code='bad_signature')


def handle_webhook(event, payload):
    """돌려주는 값 = 고친 PR 수 (연결한 저장소가 없으면 0)."""
    if event != 'pull_request':
        return 0
    pull = payload.get('pull_request') or {}
    repo_info = payload.get('repository') or {}
    owner = (repo_info.get('owner') or {}).get('login', '')
    action = payload.get('action', '')
    if action == 'closed':
        stage = GithubPullRequest.MERGED if pull.get('merged') else None
    else:
        stage = WEBHOOK_STAGE.get(action)
    count = 0
    for repo in GithubRepository.objects.filter(owner__iexact=owner, name__iexact=repo_info.get('name', '')).select_related('project'):
        save_pull(None, repo.project, {
            'repo': repo, 'number': pull.get('number') or payload.get('number'), 'title': (pull.get('title') or '')[:255],
            'head_branch': (pull.get('head') or {}).get('ref'), 'base_branch': (pull.get('base') or {}).get('ref'),
            'author_login': (pull.get('user') or {}).get('login'), 'url': pull.get('html_url'), 'stage': stage,
        }, by_webhook=True)
        count += 1
    return count


# ───────── 배포 기록 · 비교 ─────────

def versions_of(project, environment=None):
    qs = AppVersion.objects.filter(project=project).select_related('source_pr__repo')
    return qs.filter(environment=environment) if environment else qs


def version_for(project, version_id):
    v = versions_of(project).filter(pk=version_id).first()
    if v is None:
        raise NotFound('배포 기록을 찾을 수 없어요', code='version_not_found')
    return v


@transaction.atomic
def add_version(user, project, data):
    require_member(user, project)
    pr = pull_for(project, data['source_pr']) if data.get('source_pr') else None
    when = data.get('deployed_at') or timezone.now()
    version = AppVersion.objects.create(
        project=project, environment=data['environment'], version_label=data['version_label'], branch=data.get('branch') or None,
        site_url=data['site_url'], source_pr=pr, deployed_at=when,
    )
    if pr is not None and version.environment == AppVersion.PROD:
        move_stage(user, pr, GithubPullRequest.DEPLOYED, when=when)  # 서비스에 나간 PR = 배포 단계
    return version


def latest(project, environment):
    return versions_of(project, environment).first()


def compare_pair(project, base_id=None, head_id=None):
    """비교할 두 버전. 생략하면 base = 최신 prod, head = 최신 dev (팀 Figma 의 기본 화면)."""
    base = version_for(project, base_id) if base_id else latest(project, AppVersion.PROD)
    head = version_for(project, head_id) if head_id else latest(project, AppVersion.DEV)
    if base is None or head is None:
        raise NotFound('비교할 배포 기록이 두 개 있어야 해요', code='versions_missing')
    return base, head


def pulls_between(project, base, head):
    """base 배포 뒤에 병합 · 배포된 PR (= 이번 비교에서 달라진 것)."""
    lo, hi = sorted([base.deployed_at, head.deployed_at])
    return [pr for pr in pulls_of(project) if pr.merged_at and lo < pr.merged_at <= hi]


# ───────── 코멘트 ─────────

def comments_of(version, screen=None, include_resolved=True):
    qs = version.comments.select_related('author_user', 'author_role', 'resolved_by', 'card').prefetch_related('replies')
    if screen:
        qs = qs.filter(screen_name=screen)
    if not include_resolved:
        qs = qs.filter(resolved_at__isnull=True)
    return qs


def add_comment(user, version, data):
    project = version.project
    member = require_member(user, project)
    parent = None
    if data.get('parent'):
        parent = version.comments.filter(pk=data['parent']).first()
        if parent is None:
            raise NotFound('답글을 달 코멘트를 찾을 수 없어요', code='comment_not_found')
    role = match_role(project, data['role']) if data.get('role') else None
    if role is None:
        role = cards.acting_role(user, project)
    elif not is_leader(user, project) and role not in roles_of(member):
        raise Forbidden('내가 맡은 역할로만 코멘트를 남길 수 있어요', code='not_my_role')
    return CompareComment.objects.create(
        app_version=version, screen_name=(parent.screen_name if parent else data['screen'])[:100],
        pin_x=data.get('x'), pin_y=data.get('y'), author_user=user, author_role=role,
        kind=data.get('kind') or CompareComment.COMMENT, body=data['body'], parent=parent,
    )


def comment_for(project, comment_id):
    c = CompareComment.objects.filter(app_version__project=project, pk=comment_id).select_related('app_version', 'author_role').first()
    if c is None:
        raise NotFound('코멘트를 찾을 수 없어요', code='comment_not_found')
    return c


def update_comment(user, comment, data):
    project = comment.app_version.project
    require_member(user, project)
    if 'body' in data:
        if comment.author_user_id != user.pk:
            raise Forbidden('내가 쓴 코멘트만 고칠 수 있어요', code='author_only')
        comment.body = data['body']
    if 'resolved' in data:
        if data['resolved'] and comment.resolved_at is None:
            comment.resolved_at, comment.resolved_by = timezone.now(), user
        elif not data['resolved']:
            comment.resolved_at, comment.resolved_by = None, None
    comment.save()
    return comment


def delete_comment(user, comment):
    project = comment.app_version.project
    if comment.author_user_id != user.pk and not is_leader(user, project):
        raise Forbidden('내가 쓴 코멘트만 지울 수 있어요', code='author_only')
    comment.delete()


@transaction.atomic
def comment_to_request(user, comment, data):
    """코멘트 → 요청 카드 ("요청보내기로 만들기"). 고칠 쪽(fromRole)에 요청이 가요."""
    if comment.card_id:
        raise Conflict('이미 요청으로 만든 코멘트예요', code='already_requested')
    project = comment.app_version.project
    my_role = comment.author_role or cards.acting_role(user, project)
    to_role = data.get('toRole') or (my_role.role_key or str(my_role.pk) if my_role else None)
    version = comment.app_version
    card, _ = cards.create_card(user, project, {
        'id': data.get('id'), 'title': (data.get('title') or f'{comment.screen_name} 수정').strip()[:255],
        'fromRole': data['fromRole'], 'toRole': to_role, 'origin': HandoffCard.REQUEST,
        'description': f'[{version.version_label} · {comment.screen_name}] {comment.body}',
        'due': data.get('due') or '', 'checkpoint': data.get('checkpoint'), 'links': [version.site_url],
        'tag': '버전 비교',
    })
    comment.card = card
    comment.save(update_fields=['card'])
    return card


# ───────── 진행 상태 탭 ─────────

def status_summary(project):
    pulls = list(pulls_of(project))
    by_stage = {s: [p for p in pulls if p.stage == s] for s in GithubPullRequest.ORDER}
    open_comments = CompareComment.objects.filter(app_version__project=project, resolved_at__isnull=True, parent__isnull=True).count()
    card_counts = {s: 0 for s, _ in HandoffCard.STATUSES}
    for s in HandoffCard.objects.filter(project=project).values_list('status', flat=True):
        card_counts[s] += 1
    blocked = HandoffCard.objects.filter(project=project, blocked_since__isnull=False).count()
    auto = HandoffCard.objects.filter(project=project, is_auto=True).count()
    return {
        'by_stage': by_stage, 'open_comments': open_comments, 'cards': card_counts, 'blocked': blocked, 'auto_delivered': auto,
        'prod': latest(project, AppVersion.PROD), 'dev': latest(project, AppVersion.DEV),
    }
