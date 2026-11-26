"""
주소 목록. API 는 모두 /api/ 아래이고, 프론트에 맞춰 끝에 / 를 붙이지 않아요 (/api/auth/login).
앱마다 urls.py 를 만들고 여기에 한 줄씩 더해요.
"""
from django.contrib import admin
from django.urls import path

from .views import health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health', health, name='health'),
]
