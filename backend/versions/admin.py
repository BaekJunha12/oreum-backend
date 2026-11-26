from django.contrib import admin

from .models import AppVersion, CompareComment, GithubPullRequest, GithubRepository


@admin.register(GithubRepository)
class GithubRepositoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'owner', 'name', 'connected_at')


@admin.register(GithubPullRequest)
class GithubPullRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'repo', 'number', 'title', 'stage', 'updated_at')
    list_filter = ('stage',)


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'environment', 'version_label', 'deployed_at')
    list_filter = ('environment',)


@admin.register(CompareComment)
class CompareCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'app_version', 'screen_name', 'kind', 'author_user', 'resolved_at')
