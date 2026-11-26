"""프론트가 보내는 카드 모양 검사 (main2/src/data/requestStore.ts 의 HandoffCard · HistoryRecord · RequestAction)."""
from rest_framework import serializers

from projects.models import ProjectRole

from .models import EVENT_KINDS, STATUSES

# 프론트가 만드는 id: 'r' + 시간(36진수) + 번호. 글자 · 숫자 · - · _ 만 받아요.
# 카드 id 와 기록 id 를 ':' 로 이어 기록의 기본키로 쓰니까(64자) 둘 다 길이를 나눠서 제한해요.
CARD_ID = r'^[A-Za-z0-9_-]{1,40}$'
RECORD_ID = r'^[A-Za-z0-9_-]{1,23}$'
ROLE_KEYS = [k for k, _ in ProjectRole.ROLE_KEYS]
ACTIONS = ['accept', 'propose', 'acceptProposed', 'deliver', 'confirm', 'fix', 'block', 'unblock', 'comment']


class HistoryInput(serializers.Serializer):
    id = serializers.RegexField(RECORD_ID)
    kind = serializers.ChoiceField(choices=EVENT_KINDS)
    author = serializers.CharField(max_length=50, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=ROLE_KEYS)
    at = serializers.CharField(max_length=30, required=False, allow_blank=True)
    ts = serializers.IntegerField(required=False, min_value=0)
    text = serializers.CharField(allow_blank=True, max_length=5000)
    result = serializers.CharField(required=False, allow_blank=True, max_length=255)


class BlockedInput(serializers.Serializer):
    since = serializers.CharField(max_length=10)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CardInput(serializers.Serializer):
    id = serializers.RegexField(CARD_ID)
    title = serializers.CharField(max_length=255)
    fromRole = serializers.ChoiceField(choices=ROLE_KEYS)
    toRole = serializers.ChoiceField(choices=ROLE_KEYS)
    maker = serializers.CharField(max_length=50, required=False, allow_blank=True)
    requester = serializers.CharField(max_length=50, required=False, allow_blank=True)
    origin = serializers.ChoiceField(choices=['request', 'handoff'])
    links = serializers.ListField(child=serializers.CharField(max_length=700), required=False, default=list, max_length=20)
    description = serializers.CharField(required=False, allow_blank=True, default='', max_length=5000)
    checkpoint = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    due = serializers.CharField(max_length=50)
    proposedDue = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=50)
    status = serializers.ChoiceField(choices=STATUSES)
    blocked = BlockedInput(required=False, allow_null=True)
    tag = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=50)
    reviewPath = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    history = HistoryInput(many=True)

    def validate(self, attrs):
        if attrs['fromRole'] == attrs['toRole']:
            raise serializers.ValidationError('보내는 역할과 받는 역할이 같아요')
        ids = [r['id'] for r in attrs['history']]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError('기록 id 가 겹쳐요')
        return attrs


class UpdateInput(serializers.Serializer):
    """PATCH /requests/:id — { action: { type, ... }, card }"""

    action = serializers.DictField()
    card = CardInput()

    def validate_action(self, action):
        if action.get('type') not in ACTIONS:
            raise serializers.ValidationError('알 수 없는 일이에요')
        return action
