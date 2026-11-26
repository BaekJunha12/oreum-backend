from django.urls import path

from . import views

urlpatterns = [
    path('files/plan', views.PlanFileUpload.as_view(), name='plan-file'),
]
