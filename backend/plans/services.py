"""기획안 · 루트 규칙. 다른 앱(카드 · 방)도 구간 표를 직접 뒤지지 말고 이 함수들을 불러요.

자주 쓸 것
    current_checkpoint(project)        지금 구간 (새 카드 · 새 메시지의 기본 구간). 항상 구간 하나를 돌려줘요
    checkpoint_by_seq(project, seq)    프론트의 구간 번호(0 = 베이스 캠프)로 구간 찾기. 없으면 None
"""
from .models import BASE_CAMP_NAME, Checkpoint


def checkpoint_by_seq(project, seq):
    """프론트의 카드 · 메시지는 구간을 id 가 아니라 번호(seq)로 가리켜요. 그 번호의 구간 (없으면 None)."""
    return project.checkpoints.filter(seq=seq).first()


def current_checkpoint(project):
    """지금 구간. 새 카드 · 새 메시지에 구간을 따로 안 골랐을 때 붙는 구간이에요.

    아직 끝나지 않은 화면 구간(seq 1~) 중 번호가 가장 작은 것. 규칙 순서:
      1. 안 끝난 화면 구간이 있으면 그중 첫 번째 (구간끼리 겹쳐 진행돼도 앞 번호가 먼저)
      2. 화면 구간이 전부 끝났으면 마지막 화면 구간
      3. 화면 구간이 하나도 없으면 베이스 캠프 (seq 0)

    원정대가 "출발했는지"(projects.status)는 안 봐요. 프론트에는 아직 출발 호출이 없어서 status 가 늘 planning 이고,
    프론트의 기본값도 1번 구간이에요. 구간에 "도착"하는 것(arrived_at)도 지금 구간을 바꾸지 않아요 — 끝내야(completed_at) 넘어가요.
    """
    screens = project.checkpoints.filter(seq__gte=1)  # Checkpoint 는 seq 순서로 정렬돼 있어요
    return (
        screens.filter(completed_at__isnull=True).first()
        or screens.last()
        # 베이스 캠프는 원정대가 생길 때 만들어지지만(plans.signals), 지워졌어도 "항상 하나"는 지켜요
        or Checkpoint.objects.get_or_create(project=project, seq=0, defaults={'name': BASE_CAMP_NAME})[0]
    )
