from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'notifications'
    verbose_name = '알림'

    def ready(self):
        from . import signals  # noqa: F401  카드 기록이 생기면 알림을 만드는 신호를 연결해요
