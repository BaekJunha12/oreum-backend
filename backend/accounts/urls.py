from django.urls import path

from . import views

urlpatterns = [
    path('auth/login', views.Login.as_view(), name='auth-login'),
    path('auth/register', views.Register.as_view(), name='auth-register'),
    path('auth/google', views.GoogleLogin.as_view(), name='auth-google'),
    path('auth/logout', views.Logout.as_view(), name='auth-logout'),
    path('auth/me', views.Me.as_view(), name='auth-me'),
]
