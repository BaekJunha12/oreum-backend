"""요청 카드 API 가 받는 모양 (프론트 HandoffCard · RequestUpdate)."""
from rest_framework import serializers

ACTIONS = ['accept', 'propose', 'acceptProposed', 'deliver', 'confirm', 'fix', 'block', 'unblock', 'comment']


class HistoryInput(serializers.Serializer):
    id = serializers.CharField(max_length=64)
    kind = serializers.CharField(max_length=10)
    text = serializers.CharField(allow_blank=True, required=False, default='')
    result = serializers.CharField(max_length=255, required=False, allow_blank=True)


class CardInput(serializers.Serializer):
    """POST /requests — 프론트 HandoffCard (status · maker · requester 는 서버가 다시 정해요)."""

    id = serializers.CharField(max_length=64, required=False)
    title = serializers.CharField(max_length=255)
    fromRole = serializers.CharField(max_length=64)
    toRole = serializers.CharField(max_length=64)
    maker = serializers.CharField(max_length=50, required=False, allow_blank=True)
    requester = serializers.CharField(max_length=50, required=False, allow_blank=True)
    origin = serializers.ChoiceField(choices=['request', 'handoff'], default='request')
    links = serializers.ListField(child=serializers.CharField(max_length=700), required=False, default=list, max_length=20)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    checkpoint = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    due = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    tag = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    reviewPath = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    groupId = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    history = HistoryInput(many=True, required=False, default=list)


class ActionInput(serializers.Serializer):
    """RequestAction — type 마다 필요한 칸이 달라요."""

    type = serializers.ChoiceField(choices=ACTIONS)
    date = serializers.CharField(max_length=50, required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    link = serializers.CharField(max_length=700, required=False, allow_blank=True, allow_null=True)
    author = serializers.CharField(max_length=50, required=False, allow_blank=True)
    text = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=['comment', 'question'], required=False)

    def validate(self, data):
        if data['type'] == 'propose' and not (data.get('date') or '').strip():
            raise serializers.ValidationError({'date': ['제안할 날짜를 적어 주세요']})
        return data


class UpdateInput(serializers.Serializer):
    """PATCH /requests/:id — { action, card } (card 는 기록 id 를 맞추는 데만 써요)."""

    action = ActionInput(required=False)
    card = serializers.DictField(required=False)
    # action 없이 내용만 고칠 때
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    due = serializers.CharField(max_length=50, required=False)
    checkpoint = serializers.IntegerField(required=False, min_value=0)
    links = serializers.ListField(child=serializers.CharField(max_length=700), required=False, max_length=20)
    tag = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    reviewPath = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
