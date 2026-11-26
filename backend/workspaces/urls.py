from django.urls import path

from . import views

urlpatterns = [
    path('workspaces', views.Workspaces.as_view(), name='workspaces'),
]
