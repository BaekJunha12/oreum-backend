"""
모든 API 오류를 프론트와 약속한 모양으로 바꿔요.

    4xx/5xx + { "message": "보여 줄 문구", "code": "오류 종류", "errors": {...칸별 오류, 입력 오류일 때만} }

프론트(main2/src/api/http.ts)는 message 를 그대로 화면 알림에 띄우고, 401 이면 로그아웃해요.
"""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler

# DRF 기본 문구 대신 보여 줄 짧은 한국어 (직접 문구를 넣어 던진 오류는 그 문구를 그대로 씀)
FRIENDLY = {
    exceptions.NotAuthenticated: '로그인이 필요해요',
    exceptions.AuthenticationFailed: '로그인이 만료됐어요. 다시 로그인해 주세요',
    exceptions.PermissionDenied: '권한이 없어요',
    exceptions.NotFound: '찾을 수 없어요',
    exceptions.MethodNotAllowed: '지원하지 않는 요청이에요',
    exceptions.ParseError: '요청 내용을 읽지 못했어요',
}

ALWAYS_FRIENDLY = {exceptions.NotAuthenticated, exceptions.AuthenticationFailed}


def first_error(data, field=None):
    """입력 오류 묶음에서 첫 문구 하나를 꺼냄. 칸 이름이 있으면 '칸: 문구'."""
    if isinstance(data, dict):
        for key, value in data.items():
            return first_error(value, None if key == 'non_field_errors' else (f'{field}.{key}' if field else key))
        return '입력값을 확인해 주세요'
    if isinstance(data, list):
        return first_error(data[0], field) if data else '입력값을 확인해 주세요'
    return f'{field}: {data}' if field else str(data)


def message_for(exc, data):
    if isinstance(exc, exceptions.ValidationError):
        return first_error(data)
    friendly = FRIENDLY.get(type(exc))
    detail = getattr(exc, 'detail', None)
    # 로그인 문제는 원인(토큰 없음 · 틀림 · 비활성)과 상관없이 "다시 로그인" 한 문구로
    if friendly and (type(exc) in ALWAYS_FRIENDLY or str(detail) == str(exc.default_detail)):
        return friendly
    return str(detail) if detail else str(exc)


def exception_handler(exc, context):
    # DRF 와 같은 순서로 Django 기본 오류를 DRF 오류로 바꿔 둠 (문구를 고르려고)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # 예상 못 한 오류(500)는 Django 가 그대로 처리

    invalid = isinstance(exc, exceptions.ValidationError)
    body = {
        'message': message_for(exc, response.data),
        'code': 'invalid' if invalid else getattr(exc.detail, 'code', None) or exc.default_code,
    }
    if invalid:
        body['errors'] = response.data
    response.data = body
    return response
