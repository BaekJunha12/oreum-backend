from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """GET /api/health — 서버가 켜져 있는지 확인 (로그인 필요 없음)."""
    return Response({'status': 'ok'})
