"""로그인 API — 프론트 main2/src/api/index.ts 의 api.auth.* 와 1:1.

    POST /api/auth/login     { email, password }        → 200 Session
    POST /api/auth/register  { email, password, name }  → 201 Session   (프론트 화면은 아직 없음, 개발용)
    POST /api/auth/google    { credential }             → 501 (준비 중)
    POST /api/auth/logout                               → 204
    GET  /api/auth/me                                   → 200 User
"""
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .payloads import session_payload, user_payload


class BadCredentials(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = '이메일 또는 비밀번호가 틀렸어요'
    default_code = 'invalid_credentials'


class NotReady(APIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    default_detail = '아직 준비 중이에요'
    default_code = 'not_ready'


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    password = serializers.CharField(trim_whitespace=False, write_only=True)
    name = serializers.CharField(max_length=50)

    def validate_email(self, value):
        value = value.lower()
        if get_user_model().objects.filter(email=value).exists():
            raise serializers.ValidationError('이미 가입된 이메일이에요')
        return value

    def validate(self, attrs):
        user = get_user_model()(email=attrs['email'], name=attrs['name'])
        validate_password(attrs['password'], user)  # 너무 짧거나 흔한 비밀번호 막기
        return attrs


class PublicView(APIView):
    """로그인 전에 부르는 API. 쿠키 세션(관리자 화면 로그인)이 남아 있어도 CSRF 검사에 걸리지 않게 인증을 건너뛰어요."""

    authentication_classes = []
    permission_classes = [AllowAny]


class Login(PublicView):
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(request, email=s.validated_data['email'].lower(), password=s.validated_data['password'])
        if user is None:
            raise BadCredentials()
        return Response(session_payload(user))


class Register(PublicView):
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = get_user_model().objects.create_user(**s.validated_data)
        return Response(session_payload(user), status=status.HTTP_201_CREATED)


class GoogleLogin(PublicView):
    def post(self, request):
        # 구글 ID 토큰 확인은 프론트가 구글 로그인 창을 붙인 뒤에 만들어요 (UserIdentity 에 연결 저장)
        raise NotReady('구글 로그인은 아직 준비 중이에요. 이메일로 로그인해 주세요')


class Logout(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()  # 이 사용자의 토큰을 지움 = 모든 기기에서 로그아웃
        return Response(status=status.HTTP_204_NO_CONTENT)


class Me(APIView):
    def get(self, request):
        return Response(user_payload(request.user))
