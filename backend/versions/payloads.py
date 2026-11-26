"""GitHub · 버전 비교 화면 모양 (camelCase · id 는 문자열)."""
from handoffs.payloads import role_ref
from projects.payloads import iso

STAGE_LABEL = {'work': '작업', 'review': '리뷰', 'merged': '병합', 'deployed': '배포'}


def repo_payload(repo):
    return {
        'id': str(repo.pk), 'owner': repo.owner, 'name': repo.name, 'fullName': repo.full_name,
        'url': f'https://github.com/{repo.full_name}', 'installationId': repo.installation_id, 'connectedAt': iso(repo.connected_at),
    }


def pull_payload(pr):
    return {
        'id': str(pr.pk), 'repo': pr.repo.full_name, 'number': pr.number, 'title': pr.title,
        'headBranch': pr.head_branch, 'baseBranch': pr.base_branch, 'author': pr.author_login,
        'stage': pr.stage, 'stageLabel': STAGE_LABEL[pr.stage], 'url': pr.url,
        'mergedAt': iso(pr.merged_at), 'deployedAt': iso(pr.deployed_at), 'updatedAt': iso(pr.updated_at),
        'cards': [{'id': c.id, 'title': c.title, 'status': c.status, 'isAuto': c.is_auto} for c in pr.cards.all()],
    }


def version_payload(v):
    return {
        'id': str(v.pk), 'environment': v.environment, 'versionLabel': v.version_label, 'branch': v.branch,
        'siteUrl': v.site_url, 'deployedAt': iso(v.deployed_at),
        'sourcePr': {'id': str(v.source_pr_id), 'number': v.source_pr.number, 'title': v.source_pr.title, 'url': v.source_pr.url} if v.source_pr_id else None,
    }


def comment_payload(c, with_replies=True):
    out = {
        'id': str(c.pk), 'versionId': str(c.app_version_id), 'screen': c.screen_name,
        'pin': {'x': c.pin_x, 'y': c.pin_y} if c.pin_x is not None and c.pin_y is not None else None,
        'author': c.author_user.name, 'authorId': str(c.author_user_id), 'role': role_ref(c.author_role),
        'kind': c.kind, 'body': c.body, 'parentId': str(c.parent_id) if c.parent_id else None,
        'resolved': c.resolved_at is not None, 'resolvedAt': iso(c.resolved_at),
        'resolvedBy': c.resolved_by.name if c.resolved_by_id else None,
        'cardId': c.card_id, 'createdAt': iso(c.created_at),
    }
    if with_replies and c.parent_id is None:
        out['replies'] = [comment_payload(r, with_replies=False) for r in c.replies.all()]
    return out


def screens_payload(comments):
    """화면별로 묶기 → [{ screen, open, comments }] (화면 순서 = 처음 코멘트가 달린 순서)."""
    groups = {}
    for c in comments:
        if c.parent_id:
            continue
        g = groups.setdefault(c.screen_name, {'screen': c.screen_name, 'open': 0, 'comments': []})
        g['comments'].append(comment_payload(c))
        g['open'] += c.resolved_at is None
    return list(groups.values())


def status_payload(summary, project, user):
    from plans.payloads import plan_payload

    plan = plan_payload(project, user)
    return {
        'remaining': plan.get('remaining'),
        'unit': project.schedule_unit,
        'checkpoints': plan.get('checkpoints', []),
        'pulls': {stage: [pull_payload(p) for p in rows] for stage, rows in summary['by_stage'].items()},
        'pullCounts': {stage: len(rows) for stage, rows in summary['by_stage'].items()},
        'requests': {**summary['cards'], 'blocked': summary['blocked'], 'autoDelivered': summary['auto_delivered']},
        'openComments': summary['open_comments'],
        'versions': {
            'prod': version_payload(summary['prod']) if summary['prod'] else None,
            'dev': version_payload(summary['dev']) if summary['dev'] else None,
        },
    }
