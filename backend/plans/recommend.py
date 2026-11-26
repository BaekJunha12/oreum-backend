"""추천 — 기획안에서 화면 구간 뽑기 · 구간별 할 일 제안.

지금은 외부 AI 없이 규칙으로 만들어요 (키 · 비용 · 시간 제한 없이 늘 같은 답).
AI 를 붙일 때는 `recommend_checkpoints` · `suggest_tasks` 두 함수의 본문만 바꾸면 돼요 (돌려주는 모양은 그대로).

구간 뽑기 규칙
  1. 기획안 글자에서 제목(#) · 목록(-, *, 1.) 줄 중 "화면 · 페이지 · 탭 · screen · page" 가 들어간 줄을 화면으로 봐요
  2. 끝의 "화면 / 페이지" 같은 말은 떼고, 겹치는 이름은 하나만 (최대 8개)
  3. 로그인 · 회원가입은 다른 화면을 확인하려면 먼저 있어야 해서 맨 앞으로 옮기고 그 이유를 남겨요
  4. 하나도 못 찾으면 흔한 앱 흐름(로그인 · 메인 피드 · 마이페이지 · 알림)을 'ai' 출처로 추천해요
"""
import re

from .models import MAX_CHECKPOINTS

FALLBACK_ROUTE = ['로그인', '메인 피드', '마이페이지', '알림']
SCREEN_WORDS = re.compile(r'(화면|페이지|탭|screen|page)', re.I)
SKIP = {'개요', '목표', '배경', '일정', '소개', '기획', '요구사항', '참고', '팀', '역할', '마감', '기능 목록', '화면 목록', '페이지 목록', '화면 구성', 'mvp'}
LIST_LINE = re.compile(r'^\s*(?:#{1,6}\s+|[-*•]\s+|\d+[.)]\s+)(.+?)\s*$')
TAIL = re.compile(r'\s+(화면|페이지|탭|screen|page)\s*$', re.I)
AUTH = ('로그인', '회원가입', '온보딩', 'login', 'sign')


def _clean(line):
    line = re.sub(r'[`*_>\[\]]', '', line)
    line = re.split(r'\s[-–—:|]\s|[:(（]', line)[0]  # '로그인 화면 - 이메일로 ...' → '로그인 화면'
    line = TAIL.sub('', line.strip())
    return line.strip(' .')


def screens_from_text(text):
    """기획안 글자 → 화면 이름 목록 (순서 유지, 겹침 제거)."""
    found = []
    for raw in (text or '').splitlines():
        m = LIST_LINE.match(raw)
        if not m or not SCREEN_WORDS.search(m.group(1)):
            continue
        name = _clean(m.group(1))
        if not name or len(name) > 30 or name.lower() in SKIP or name in found:
            continue
        found.append(name)
    return found


def recommend_checkpoints(text):
    """기획안 글자 → [{ name, source, reason }] (베이스 캠프 · 정상 빼고, 최대 8개)."""
    names = screens_from_text(text)
    if not names:
        return [{'name': n, 'source': 'ai', 'reason': None} for n in FALLBACK_ROUTE]

    auth = [n for n in names if n.lower().startswith(AUTH)]
    rest = [n for n in names if n not in auth]
    ordered = (auth + rest)[:MAX_CHECKPOINTS]
    out = []
    for i, name in enumerate(ordered):
        moved = name in auth and names.index(name) != i
        out.append({
            'name': name,
            'source': 'plan',
            'reason': '다른 화면을 확인하려면 먼저 로그인이 되어야 해서 앞으로 옮겼어요' if moved else None,
        })
    return out


# ───────── 구간별 할 일 ─────────

TEMPLATES = {
    # 역할 키 → (기획안에서 바로 나오는 일 = plan · 담김, AI 가 덧붙이는 일 = ai · 제안)
    'design': ('{name} 화면 시안', '{name} 화면 접근성 점검 (대비 · 글자 크기)'),
    'front': ('{name} 화면 구현', '{name} API 연결 · 오류 화면'),
    'back': ('{name} API 만들기', '{name} API 명세 공유'),
}
BASE_CAMP = {
    'design': ('디자인 시스템 정하기 (색 · 글꼴 · 버튼)', '화면 흐름도 그리기'),
    'front': ('프로젝트 세팅 · 라우팅', '공용 컴포넌트 만들기'),
    'back': ('DB 설계 · 서버 세팅', '로그인 토큰 방식 정하기'),
}


def suggest_tasks(checkpoint, roles, blocked_cards=()):
    """구간 하나의 할 일 제안 → [{ role, title, origin, reason }].

    blocked_cards = 앞 구간에서 막힌 카드 (도착할 때 막힘 · 지연을 반영하는 자리, ERD checkpoints.arrived_at)
    """
    out = []
    for role in roles:
        key = role.role_key
        if checkpoint.seq == 0:
            plan_title, ai_title = BASE_CAMP.get(key, (f'{role.label} 작업 준비', f'{role.label} 작업 방식 정하기'))
        else:
            plan_t, ai_t = TEMPLATES.get(key, ('{name} ' + role.label + ' 작업', '{name} ' + role.label + ' 검토'))
            plan_title, ai_title = plan_t.format(name=checkpoint.name), ai_t.format(name=checkpoint.name)
        out.append({'role': role, 'title': plan_title, 'origin': 'plan', 'reason': None})
        out.append({'role': role, 'title': ai_title, 'origin': 'ai', 'reason': f'"{checkpoint.name}" 구간에서 {role.label}가 자주 놓치는 일이에요'})
        for card in blocked_cards:
            if card.to_role_id == role.pk or card.from_role_id == role.pk:
                out.append({
                    'role': role, 'title': f'막힌 요청 먼저 풀기: {card.title}', 'origin': 'ai',
                    'reason': '앞 구간에서 막힌 요청이라 이번 구간 일을 늦출 수 있어요',
                })
    return out
