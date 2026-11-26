"""원정대 규칙을 어겼을 때 던지는 오류. 문구가 그대로 프론트 알림에 나와요 ({ message, code })."""
from rest_framework import status
from rest_framework.exceptions import APIException


class ProjectError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = '요청을 처리하지 못했어요'
    default_code = 'project_error'


class Forbidden(ProjectError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = 'forbidden'


class NotFound(ProjectError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = 'not_found'


class Conflict(ProjectError):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'conflict'


class Gone(ProjectError):
    """이제는 쓸 수 없는 것 (만료 · 취소된 초대)."""

    status_code = status.HTTP_410_GONE
    default_code = 'gone'
