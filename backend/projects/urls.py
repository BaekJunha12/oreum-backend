from django.urls import path

from . import views

urlpatterns = [
    path('projects', views.Projects.as_view(), name='projects'),
    path('projects/<int:project_id>', views.ProjectDetail.as_view(), name='project-detail'),
    path('projects/<int:project_id>/invitations', views.Invitations.as_view(), name='project-invitations'),
    path('projects/<int:project_id>/invitations/<int:invitation_id>/revoke', views.RevokeInvitation.as_view(), name='invitation-revoke'),
    path('projects/<int:project_id>/retrospectives', views.Retrospectives.as_view(), name='project-retrospectives'),
    path('invitations/<str:token>', views.InvitationByToken.as_view(), name='invitation'),
    path('invitations/<str:token>/accept', views.AcceptInvitation.as_view(), name='invitation-accept'),
]
