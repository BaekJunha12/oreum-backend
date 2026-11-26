"""넘겨주기 카드 API — 프론트 main2/src/api/index.ts 의 api.requests.* 와 1:1.

    GET   /api/requests       지금 원정대의 카드 목록 → HandoffCard[]
    POST  /api/requests       새 카드 (id 는 프론트가 만들어 보냄) → 201 HandoffCard
    PATCH /api/requests/<id>  { action, card } → HandoffCard
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .payloads import card_payload, cards_payload
from .serializers import CardInput, UpdateInput


class Requests(APIView):
    def get(self, request):
        return Response(cards_payload(services.cards_for(request.user)))

    def post(self, request):
        s = CardInput(data=request.data)
        s.is_valid(raise_exception=True)
        card = services.create_card(request.user, s.validated_data)
        return Response(card_payload(card), status=status.HTTP_201_CREATED)


class RequestDetail(APIView):
    def patch(self, request, card_id):
        s = UpdateInput(data=request.data)
        s.is_valid(raise_exception=True)
        card = services.update_card(request.user, card_id, s.validated_data['action'], s.validated_data['card'])
        return Response(card_payload(card))
