from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """프론트가 보내는 `Authorization: Bearer <토큰>` 을 읽어요 (DRF 기본은 `Token <토큰>`).

    토큰이 없으면 401 + `WWW-Authenticate: Bearer` 를 돌려줘서, 프론트가 로그아웃 처리를 할 수 있어요.
    """

    keyword = 'Bearer'
