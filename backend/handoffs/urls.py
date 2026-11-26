from django.urls import path

from . import views

urlpatterns = [
    path('requests', views.Requests.as_view(), name='requests'),
    path('requests/reset', views.RequestsReset.as_view(), name='requests-reset'),
    path('requests/<str:card_id>', views.RequestDetail.as_view(), name='request'),
]
