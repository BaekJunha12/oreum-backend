from django.urls import path

from . import views

urlpatterns = [
    path('plan', views.Plan.as_view(), name='plan'),
    path('plan/document', views.Document.as_view(), name='plan-document'),
    path('plan/documents', views.DocumentHistory.as_view(), name='plan-documents'),
    path('files/plan', views.PlanFileUpload.as_view(), name='plan-file'),
    path('files/plan/<int:document_id>', views.PlanFileDownload.as_view(), name='plan-file-download'),
    path('route', views.Route.as_view(), name='route'),
    path('route/recommend', views.RouteRecommend.as_view(), name='route-recommend'),
    path('route/start', views.RouteStart.as_view(), name='route-start'),
    path('route/summit', views.RouteSummit.as_view(), name='route-summit'),
    path('checkpoints/<int:seq>', views.CheckpointDetail.as_view(), name='checkpoint'),
    path('checkpoints/<int:seq>/complete', views.CheckpointComplete.as_view(), name='checkpoint-complete'),
    path('checkpoints/<int:seq>/reopen', views.CheckpointReopen.as_view(), name='checkpoint-reopen'),
    path('checkpoints/<int:seq>/tasks', views.CheckpointTasks.as_view(), name='checkpoint-tasks'),
    path('tasks/<int:task_id>', views.TaskDetail.as_view(), name='task'),
]
