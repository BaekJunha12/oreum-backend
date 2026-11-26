from django.urls import path

from . import views

urlpatterns = [
    path('notifications', views.Notifications.as_view(), name='notifications'),
    path('notifications/read', views.MarkRead.as_view(), name='notifications-read'),
]
