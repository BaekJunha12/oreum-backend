"""프론트와 주고받는 사용자 모양 (main2/src/data/sessionStore.ts 의 User · Session)."""
from rest_framework.authtoken.models import Token

# 프론트는 role 이 design · front · back 중 하나가 아니면 저장된 로그인을 버려요(새로고침하면 로그아웃).
# 아직 원정대에서 역할을 받지 않은 사용자는 이 값으로 보내요. (팀 결정 전 임시값 — README "정할 것")
FALLBACK_ROLE = 'design'


def role_of(user):
    """지금 원정대에서 맡은 첫 기본 역할 (projects.services.current_project 참고)."""
    from projects.services import primary_role_key  # projects 가 accounts 를 가져다 쓰므로 여기서만 늦게 가져옴

    return primary_role_key(user) or FALLBACK_ROLE


def user_payload(user):
    """User { id, name, email, role } — id 는 프론트 타입에 맞춰 글자로 보내요."""
    return {'id': str(user.pk), 'name': user.name, 'email': user.email, 'role': role_of(user)}


def session_payload(user):
    """Session { token, user } — 로그인 · 가입 응답."""
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'user': user_payload(user)}
