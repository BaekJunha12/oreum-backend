"""기획안 · 루트 API. 모양은 프론트 main2/src/api/types.ts 그대로 (+ 몇 칸 더).

    GET  /api/plan                         일정 (원정대가 없으면 기본값)                       Plan
    PUT  /api/plan                         일정 저장 (리더, 원정대가 없으면 만듦)              Plan → Plan
    POST /api/files/plan                   기획안 파일 올리기 (multipart, 칸 이름 file)        → PlanFile
    GET  /api/files/plan/<id>              기획안 파일 내려받기 (원정대원)
    GET  /api/plan/document                지금 기획 문서 (없으면 exists: false + 안내 문구)
    PUT  /api/plan/document                기획 문서 고치기 { text } 또는 { url } (리더, 새 판으로 저장)
    DELETE /api/plan/document              기획 문서 비우기 (리더)
    GET  /api/plan/documents               기획 문서 판 목록 (최근 것부터)
    POST /api/route/recommend              AI 추천 루트 { deadline, roles, source } → { checkpoints }
    GET  /api/route                        루트 상세 (구간 · 역할별 할 일 · 진행률)
    POST /api/route/start                  이 루트로 출발하기 (리더)
    POST /api/route/summit                 정상 도착 (리더, 모든 구간이 끝나야 함)
    PATCH /api/checkpoints/<seq>           구간 기간 고치기 { startAt, endAt } (리더)
    POST /api/checkpoints/<seq>/complete   구간 완료 (리더) → 다음 구간 도착 · 할 일 추천
    POST /api/checkpoints/<seq>/reopen     구간 완료 취소 (리더)
    GET  /api/checkpoints/<seq>/tasks      구간 할 일
    POST /api/checkpoints/<seq>/tasks      할 일 더하기 { role, title, assigneeMemberId? }
    PATCH /api/tasks/<id>                  할 일 고르기 · 끝내기 { state?, title?, assigneeMemberId? }
    DELETE /api/tasks/<id>                 할 일 지우기
"""
import mimetypes

from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.errors import NotFound
from projects.models import ProjectMember
from projects.services import match_role, project_context

from . import schedule, services
from .models import PlanDocument
from .payloads import checkpoint_payload, default_plan, document_payload, plan_file_payload, plan_payload, route_payload, task_payload
from .serializers import (
    CheckpointDatesInput, DocumentInput, PlanInput, RouteRecommendInput, TaskInput, TaskUpdateInput,
)


def _valid(serializer_class, request):
    s = serializer_class(data=request.data)
    s.is_valid(raise_exception=True)
    return s.validated_data


class Plan(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        return Response(plan_payload(project, request.user) if project else default_plan())

    def put(self, request):
        d = _valid(PlanInput, request)
        project, _ = project_context(request, required=False)
        project = services.save_plan(
            request.user, project,
            deadline_at=schedule.combine(d['date'], d['time']), unit=d['unit'], roles=d['roles'],
            checkpoints=d['checkpoints'], generated_from=d.get('generatedFrom'), name=d.get('projectName'),
        )
        project.refresh_from_db()
        return Response(plan_payload(project, request.user))


class PlanFileUpload(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            raise ValidationError('기획안 파일을 골라 주세요')
        project, _ = project_context(request, required=False)
        doc = services.save_plan_file(request.user, project, upload)
        return Response(plan_file_payload(doc), status=status.HTTP_201_CREATED)


class PlanFileDownload(APIView):
    def get(self, request, document_id):
        project, _ = project_context(request)
        doc = services.document_for_member(request.user, project, document_id)
        if doc.source_type != PlanDocument.FILE or not doc.storage_url or not default_storage.exists(doc.storage_url):
            raise NotFound('파일을 찾을 수 없어요', code='plan_file_not_found')
        content_type = doc.mime_type or mimetypes.guess_type(doc.file_name or '')[0] or 'application/octet-stream'
        return FileResponse(default_storage.open(doc.storage_url, 'rb'), as_attachment=True, filename=doc.file_name, content_type=content_type)


class Document(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        return Response(document_payload(services.current_document(project)))

    def put(self, request):
        d = _valid(DocumentInput, request)
        project, _ = project_context(request, required=False)
        if 'url' in d:
            doc = services.save_plan_link(request.user, project, d['url'])
        else:
            doc = services.save_plan_text(request.user, project, d['text'])
        return Response(document_payload(doc))

    def delete(self, request):
        project, _ = project_context(request)
        services.clear_document(request.user, project)
        return Response(document_payload(None))


class DocumentHistory(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        if project is None:
            return Response([])
        docs = project.plan_documents.select_related('uploaded_by')[:50]
        return Response([document_payload(d, with_text=False) for d in docs])


class RouteRecommend(APIView):
    def post(self, request):
        d = _valid(RouteRecommendInput, request)
        project, _ = project_context(request, required=False)
        deadline = d['deadline']
        picks = services.recommend_route(
            request.user, project, deadline_at=schedule.combine(deadline['date'], deadline['time']),
            unit=deadline['unit'], roles=d['roles'], source=d['source'],
        )
        return Response({'checkpoints': picks})


class Route(APIView):
    def get(self, request):
        project, _ = project_context(request)
        return Response(route_payload(project, request.user))


class RouteStart(APIView):
    def post(self, request):
        project, _ = project_context(request)
        project = services.start_route(request.user, project)
        return Response(route_payload(project, request.user))


class RouteSummit(APIView):
    def post(self, request):
        project, _ = project_context(request)
        project = services.reach_summit(request.user, project)
        return Response(route_payload(project, request.user))


class CheckpointDetail(APIView):
    def patch(self, request, seq):
        d = _valid(CheckpointDatesInput, request)
        project, _ = project_context(request)
        cp = services.set_checkpoint_dates(request.user, project, seq, d['startAt'], d['endAt'])
        return Response(checkpoint_payload(cp, project, services.current_checkpoint(project)))


class CheckpointComplete(APIView):
    def post(self, request, seq):
        project, _ = project_context(request)
        services.complete_checkpoint(request.user, project, seq)
        return Response(route_payload(project, request.user))


class CheckpointReopen(APIView):
    def post(self, request, seq):
        project, _ = project_context(request)
        services.reopen_checkpoint(request.user, project, seq)
        return Response(route_payload(project, request.user))


def _member(project, member_id):
    if member_id is None:
        return None
    m = ProjectMember.objects.filter(project=project, pk=member_id).select_related('user').first()
    if m is None:
        raise NotFound('원정대원을 찾을 수 없어요', code='member_not_found')
    return m


class CheckpointTasks(APIView):
    def get(self, request, seq):
        project, _ = project_context(request)
        cp = services.checkpoint_by_seq(project, seq)
        if cp is None:
            raise NotFound('구간을 찾을 수 없어요', code='checkpoint_not_found')
        tasks = cp.tasks.select_related('checkpoint', 'role', 'assignee_member__user')
        return Response([task_payload(t) for t in tasks])

    def post(self, request, seq):
        d = _valid(TaskInput, request)
        project, _ = project_context(request)
        role = match_role(project, d['role'])
        if role is None:
            raise NotFound('역할을 찾을 수 없어요', code='role_not_found')
        task = services.add_task(request.user, project, seq, role=role, title=d['title'], assignee=_member(project, d.get('assigneeMemberId')))
        return Response(task_payload(task), status=status.HTTP_201_CREATED)


class TaskDetail(APIView):
    def patch(self, request, task_id):
        d = _valid(TaskUpdateInput, request)
        project, _ = project_context(request)
        task = services.task_for(request.user, project, task_id)
        assignee = _member(project, d['assigneeMemberId']) if 'assigneeMemberId' in d else ...
        task = services.update_task(task, state=d.get('state'), title=d.get('title'), assignee=assignee)
        return Response(task_payload(task))

    def delete(self, request, task_id):
        project, _ = project_context(request)
        services.task_for(request.user, project, task_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
