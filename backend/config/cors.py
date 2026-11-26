"""
CORS: 다른 주소(포트)에서 뜬 프론트가 브라우저로 이 API를 부를 수 있게 허락하는 응답 머리말.

프론트(http://localhost:5183)와 서버(http://localhost:8000)는 포트가 달라서 브라우저가 "다른 사이트"로 봐요.
브라우저는 먼저 OPTIONS 로 "보내도 돼?" 하고 묻고(사전 확인), 서버가 허락해야 진짜 요청을 보내요.
프론트는 credentials: 'include' 로 보내기 때문에 Allow-Origin 에 * 를 쓸 수 없고, 주소를 정확히 돌려줘야 해요.

허용 주소: settings.CORS_ALLOWED_ORIGINS (환경 변수 CORS_ALLOWED_ORIGINS 로 바꿀 수 있음)
"""
from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers

ALLOW_METHODS = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
DEFAULT_HEADERS = 'authorization, content-type, accept'


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin')
        allowed = origin is not None and origin in settings.CORS_ALLOWED_ORIGINS

        if allowed and request.method == 'OPTIONS' and 'Access-Control-Request-Method' in request.headers:
            # 사전 확인: 뷰까지 가지 않고 바로 "보내도 돼요"
            response = HttpResponse(status=204)
            response['Access-Control-Allow-Methods'] = ALLOW_METHODS
            response['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', DEFAULT_HEADERS)
            response['Access-Control-Max-Age'] = '600'
        else:
            response = self.get_response(request)

        if allowed:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
        patch_vary_headers(response, ['Origin'])
        return response
