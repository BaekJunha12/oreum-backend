"""
주소 목록. API 는 모두 /api/ 아래이고, 프론트에 맞춰 끝에 / 를 붙이지 않아요 (/api/auth/login).
앱마다 urls.py 를 만들고 여기에 한 줄씩 더해요.
"""
from django.contrib import admin
from django.urls import include, path, re_path

from .views import api_not_found, health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health', health, name='health'),
    path('api/', include('accounts.urls')),
    path('api/', include('workspaces.urls')),
    path('api/', include('projects.urls')),
    path('api/', include('handoffs.urls')),
    path('api/', include('notifications.urls')),
    re_path(r'^api/', api_not_found),  # 맨 끝: 위에서 못 찾은 /api/ 주소
]
