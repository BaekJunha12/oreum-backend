"""요청 카드 API — 프론트 api.requests.*

    GET    /api/requests              카드 목록 (?status= · ?role= · ?checkpoint= · ?open=1 로 걸러 보기)   → HandoffCard[]
    POST   /api/requests              새 요청 · 바로 보내기(origin=handoff)                                  HandoffCard → HandoffCard
    GET    /api/requests/<id>         카드 하나
    PATCH  /api/requests/<id>         한 일 { action, card } → HandoffCard (또는 action 없이 title · due … 고치기)
    DELETE /api/requests/<id>         지우기 (만든 사람 · 리더)
    POST   /api/requests/reset        예시 카드로 되돌리기 (리더, 개발 서버(DEBUG)에서만)
"""
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.errors import Forbidden
from projects.services import match_role, project_context

from . import services
from .payloads import card_payload, cards_payload
from .serializers import CardInput, UpdateInput

UPDATABLE = ('title', 'description', 'due', 'checkpoint', 'links', 'tag', 'reviewPath')


class Requests(APIView):
    def get(self, request):
        project, _ = project_context(request, required=False)
        if project is None:
            return Response([])
        cards = services.cards_of(project)
        q = request.query_params
        if q.get('status'):
            cards = cards.filter(status__in=q['status'].split(','))
        if q.get('open') in ('1', 'true'):
            cards = cards.exclude(status='confirmed')
        if q.get('checkpoint', '').isdigit():
            cards = cards.filter(checkpoint__seq=int(q['checkpoint']))
        if q.get('role'):
            role = match_role(project, q['role'])
            cards = cards.filter(from_role=role) | cards.filter(to_role=role) if role else cards.none()
        return Response(cards_payload(cards))

    def post(self, request):
        s = CardInput(data=request.data)
        s.is_valid(raise_exception=True)
        project, _ = project_context(request)
        card, merged = services.create_card(request.user, project, s.validated_data)
        card = services.card_for(request.user, project, card.pk)
        return Response(card_payload(card), status=status.HTTP_200_OK if merged else status.HTTP_201_CREATED)


class RequestDetail(APIView):
    def get(self, request, card_id):
        project, _ = project_context(request)
        return Response(card_payload(services.card_for(request.user, project, card_id)))

    def patch(self, request, card_id):
        s = UpdateInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        project, _ = project_context(request)
        card = services.card_for(request.user, project, card_id)
        if 'action' in d:
            services.apply_action(request.user, card, d['action'], d.get('card'))
        elif any(k in d for k in UPDATABLE):
            services.update_fields(request.user, card, {k: d[k] for k in UPDATABLE if k in d})
        return Response(card_payload(services.card_for(request.user, project, card_id)))

    def delete(self, request, card_id):
        project, _ = project_context(request)
        services.delete_card(request.user, services.card_for(request.user, project, card_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class RequestsReset(APIView):
    def post(self, request):
        if not settings.DEBUG:
            raise Forbidden('예시 데이터 되돌리기는 개발 서버에서만 돼요', code='debug_only')
        project, _ = project_context(request)
        return Response(cards_payload(services.reset_demo(request.user, project)))
