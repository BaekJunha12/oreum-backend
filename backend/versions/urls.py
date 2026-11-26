from django.urls import path

from . import views

urlpatterns = [
    path('github', views.Github.as_view(), name='github'),
    path('github/repos', views.Repos.as_view(), name='github-repos'),
    path('github/repos/<int:repo_id>', views.RepoDetail.as_view(), name='github-repo'),
    path('github/pulls', views.Pulls.as_view(), name='github-pulls'),
    path('github/pulls/<int:pr_id>', views.PullDetail.as_view(), name='github-pull'),
    path('github/webhook', views.GithubWebhook.as_view(), name='github-webhook'),
    path('versions', views.Versions.as_view(), name='versions'),
    path('versions/compare', views.Compare.as_view(), name='versions-compare'),
    path('versions/<int:version_id>/comments', views.VersionComments.as_view(), name='version-comments'),
    path('compare-comments/<int:comment_id>', views.CommentDetail.as_view(), name='compare-comment'),
    path('compare-comments/<int:comment_id>/request', views.CommentRequest.as_view(), name='compare-comment-request'),
    path('status', views.Status.as_view(), name='status'),
]
