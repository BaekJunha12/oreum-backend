"""기획안 · 루트 API. 모양은 프론트 main2/src/api/types.ts 그대로예요.

    POST /api/files/plan     기획안 파일 올리기 (multipart, 칸 이름 file) → PlanFile (리더만)
"""
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .payloads import plan_file_payload


class PlanFileUpload(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            raise ValidationError('기획안 파일을 골라 주세요')
        doc = services.save_plan_file(request.user, upload)
        return Response(plan_file_payload(doc), status=status.HTTP_201_CREATED)
