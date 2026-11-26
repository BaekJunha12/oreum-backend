"""기획안 · 루트 API 가 받는 모양 (프론트 main2/src/api/types.ts)."""
import re

from rest_framework import serializers

from projects.models import ProjectRole

from .models import MAX_CHECKPOINTS, CheckpointTask, PlanDocument

LINK = re.compile(r'^https?://\S+\.\S+$')  # 프론트 StartPage 의 링크 확인과 같아요


class RoleInput(serializers.Serializer):
    """프론트 PlanRole { id, label, people, role? }."""

    id = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    label = serializers.CharField(max_length=30)
    people = serializers.IntegerField(min_value=0, max_value=20, default=1)
    role = serializers.ChoiceField(choices=[k for k, _ in ProjectRole.ROLE_KEYS], required=False, allow_null=True)


def validate_roles(roles):
    labels = [r['label'].strip() for r in roles]
    keys = [r['role'] for r in roles if r.get('role')]
    if len(set(labels)) != len(labels):
        raise serializers.ValidationError('역할 이름이 겹쳐요')
    if len(set(keys)) != len(keys):
        raise serializers.ValidationError('디자인 · 프론트 · 백은 한 번씩만 넣을 수 있어요')
    return roles


class CheckpointInput(serializers.Serializer):
    """프론트 PlanCheckpoint { id, name } (+ 고른 기간 startAt · endAt 은 있어도 되고 없어도 돼요)."""

    id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    name = serializers.CharField(max_length=100)
    startAt = serializers.DateTimeField(required=False, allow_null=True)
    endAt = serializers.DateTimeField(required=False, allow_null=True)
    source = serializers.ChoiceField(choices=['plan', 'ai', 'manual'], required=False)


class PlanInput(serializers.Serializer):
    """PUT /plan — 프론트 Plan { unit, date, time, roles, checkpoints, generatedFrom? }."""

    unit = serializers.ChoiceField(choices=['day', 'hour'])
    date = serializers.DateField()
    time = serializers.TimeField(input_formats=['%H:%M', '%H:%M:%S'])
    roles = RoleInput(many=True)
    checkpoints = CheckpointInput(many=True)
    generatedFrom = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    projectName = serializers.CharField(max_length=100, required=False)

    def validate_roles(self, roles):
        if not roles:
            raise serializers.ValidationError('역할을 하나 이상 넣어 주세요')
        return validate_roles(roles)

    def validate_checkpoints(self, items):
        if len(items) > MAX_CHECKPOINTS:
            raise serializers.ValidationError(f'체크포인트는 최대 {MAX_CHECKPOINTS}개까지예요')
        return items


class DeadlineInput(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField(input_formats=['%H:%M', '%H:%M:%S'])
    unit = serializers.ChoiceField(choices=['day', 'hour'])


class PlanSourceInput(serializers.Serializer):
    """프론트 PlanSource: 파일 { type, name, fileId? } · 링크 { type, url } · 직접 입력 { type, text }."""

    type = serializers.ChoiceField(choices=[k for k, _ in PlanDocument.SOURCE_TYPES])
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    fileId = serializers.CharField(max_length=20, required=False, allow_blank=True)
    url = serializers.CharField(max_length=700, required=False, allow_blank=True)
    text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)

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


class DocumentInput(serializers.Serializer):
    """PUT /plan/document — 글로 고치거나 { url } 로 링크를 바꿔요."""

    text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    url = serializers.CharField(max_length=700, required=False)

    def validate(self, data):
        if 'url' in data:
            data['url'] = data['url'].strip()
            if not LINK.match(data['url']):
                raise serializers.ValidationError('링크는 https:// 로 시작하는 주소로 넣어 주세요')
        elif 'text' not in data:
            raise serializers.ValidationError('text 또는 url 을 보내 주세요')
        elif not data['text'].strip():
            raise serializers.ValidationError('기획 문서를 비우려면 DELETE /plan/document 를 써 주세요')
        return data


class CheckpointDatesInput(serializers.Serializer):
    startAt = serializers.DateTimeField(allow_null=True)
    endAt = serializers.DateTimeField(allow_null=True)


class TaskInput(serializers.Serializer):
    role = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=255)
    assigneeMemberId = serializers.IntegerField(required=False, allow_null=True)


class TaskUpdateInput(serializers.Serializer):
    state = serializers.ChoiceField(choices=[k for k, _ in CheckpointTask.STATES], required=False)
    title = serializers.CharField(max_length=255, required=False)
    assigneeMemberId = serializers.IntegerField(required=False, allow_null=True)
