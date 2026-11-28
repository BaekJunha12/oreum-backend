"""기획안 API 가 받는 모양 (프론트 main2/src/api/types.ts)."""
import re

from rest_framework import serializers

from projects.views import RoleInput  # 프론트 PlanRole { id, label, people, role? } — A 가 이미 같은 모양으로 받고 있어요

from .models import PlanDocument

LINK = re.compile(r'^https?://\S+\.\S+$')  # 프론트 StartPage 의 링크 확인과 같아요


def validate_roles(roles):
    """역할 이름은 겹치면 안 되고, 디자인 · 프론트 · 백은 한 번씩만 (A 의 CreateProjectInput.validate_roles 와 같은 규칙)."""
    labels = [r['label'] for r in roles]
    keys = [r['role'] for r in roles if r.get('role')]
    if len(set(labels)) != len(labels):
        raise serializers.ValidationError('역할 이름이 겹쳐요')
    if len(set(keys)) != len(keys):
        raise serializers.ValidationError('디자인 · 프론트 · 백은 한 번씩만 넣을 수 있어요')
    return roles


class DeadlineInput(serializers.Serializer):
    """프론트 { date: 'YYYY-MM-DD', time: 'HH:MM', unit: 'day' | 'hour' }."""

    date = serializers.DateField()
    time = serializers.TimeField()
    unit = serializers.ChoiceField(choices=['day', 'hour'])


class PlanSourceInput(serializers.Serializer):
    """프론트 PlanSource: 파일 { type, name, fileId? } · 링크 { type, url } · 직접 입력 { type, text }."""

    type = serializers.ChoiceField(choices=[k for k, _ in PlanDocument.SOURCE_TYPES])
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    fileId = serializers.CharField(max_length=20, required=False, allow_blank=True)
    url = serializers.CharField(max_length=700, required=False, allow_blank=True)
    text = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data['type'] == PlanDocument.LINK:
            data['url'] = data.get('url', '').strip()
            if not LINK.match(data['url']):
                raise serializers.ValidationError('기획안 링크는 https:// 로 시작하는 주소로 넣어 주세요')
        elif data['type'] == PlanDocument.TEXT:
            data['text'] = data.get('text', '').strip()
            if not data['text']:
                raise serializers.ValidationError('기획 내용을 적어 주세요')
        return data


class RouteRecommendInput(serializers.Serializer):
    deadline = DeadlineInput()
    roles = RoleInput(many=True)
    source = PlanSourceInput()

    def validate_roles(self, roles):
        return validate_roles(roles)
