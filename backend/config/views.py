from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """GET /api/health — 서버가 켜져 있는지 확인 (로그인 필요 없음)."""
    return Response({'status': 'ok'})


@api_view(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([])
@permission_classes([AllowAny])
def api_not_found(request):
    """/api/ 아래의 없는 주소. HTML 404 대신 { message } 로 답해서, 프론트 알림에 어떤 API 가 없는지 보여요."""
    raise NotFound(f'아직 없는 API 예요 ({request.method} {request.path})', code='no_such_api')
