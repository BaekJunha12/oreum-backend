from django.urls import path

from . import views

urlpatterns = [
    path('rooms', views.Rooms.as_view(), name='rooms'),
    path('rooms/<str:room_key>/messages', views.RoomMessages.as_view(), name='room-messages'),
    path('rooms/<str:room_key>/read', views.RoomRead.as_view(), name='room-read'),
]
