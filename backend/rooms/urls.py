from django.urls import path

from . import views

urlpatterns = [
    path('rooms/<str:room>/messages', views.Messages.as_view(), name='room-messages'),
]
