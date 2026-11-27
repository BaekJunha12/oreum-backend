from django.apps import AppConfig


class PlansConfig(AppConfig):
    name = 'plans'
    verbose_name = '기획안 · 루트'

    def ready(self):
        from . import signals  # noqa: F401  원정대가 생기면 베이스 캠프를 만드는 신호를 연결해요
