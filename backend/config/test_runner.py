from django.conf import settings
from django.test.runner import DiscoverRunner


class BackendDiscoverRunner(DiscoverRunner):
    """어느 폴더에서 실행해도 backend/ 안의 테스트를 찾아요.

    Django 기본은 "지금 있는 폴더"에서 테스트를 찾아서, 저장소 맨 위에서
    `python backend/manage.py test` 를 하면 NO TESTS RAN 이 나와요. 그걸 막아요.
    `python backend/manage.py test projects` 처럼 앱 이름을 주면 그 앱만 돌려요.
    """

    def build_suite(self, test_labels=None, **kwargs):
        return super().build_suite(test_labels or [str(settings.BASE_DIR)], **kwargs)
