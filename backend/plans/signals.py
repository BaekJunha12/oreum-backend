from django.db.models.signals import post_save
from django.dispatch import receiver

from projects.models import Project

from .models import BASE_CAMP_NAME, Checkpoint


@receiver(post_save, sender=Project)
def create_base_camp(sender, instance, created, raw=False, **kwargs):
    """원정대가 생기면 베이스 캠프(seq 0)를 같이 만들어요. ERD: 원정대마다 "항상 있음".

    projects 앱 코드를 고치지 않고 지키려고 신호로 해요. 이미 있던 원정대는 0001 마이그레이션이 채워 줘요.
    """
    if created and not raw:  # raw = loaddata (그 파일에 구간도 들어 있음)
        Checkpoint.objects.create(project=instance, seq=0, name=BASE_CAMP_NAME)
