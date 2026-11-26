"""다른 앱 테스트에서도 쓰는 원정대 준비 도우미.

    from projects.testing import make_project
    project, leader = make_project()                      # 디자인 · 프론트 · 백 1명씩, 리더는 디자인
    member = add_to(project, 'front@example.com', 'front')  # 프론트 원정대원 한 명 더
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import ProjectRole
from .services import create_project, join_project


def make_user(email, name=None):
    return get_user_model().objects.create_user(email, 'climb-the-oreum-2026', name=name or email.split('@')[0])


def make_project(leader=None, name='캠퍼스 앱', leader_role='design', roles=None):
    leader = leader or make_user('leader@example.com', '리더')
    project = create_project(leader, name=name, deadline_at=timezone.now() + timedelta(days=14), roles=roles, my_roles=[leader_role] if leader_role else [])
    return project, leader


def add_to(project, email, *role_keys, name=None):
    user = make_user(email, name)
    return join_project(user, project, ProjectRole.objects.filter(project=project, role_key__in=role_keys))


def api_as(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.get_or_create(user=user)[0].key}')
    return client
