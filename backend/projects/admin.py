from django.contrib import admin

from .models import Project, ProjectInvitation, ProjectMember, ProjectRole
from .services import invitation_roles, roles_of

# 기본키가 두 칸인 표(project_member_roles, invitation_roles)는 관리자 화면에 따로 올릴 수 없어서
# 원정대원 · 초대 화면에 읽기 전용으로 보여 줘요. 역할 배정은 API(초대 받기)로 해요.


class RoleInline(admin.TabularInline):
    model = ProjectRole
    extra = 0
    fields = ('label', 'role_key', 'headcount', 'sort_order')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'workspace', 'status', 'deadline_at', 'created_by')
    list_filter = ('status',)
    search_fields = ('name',)
    inlines = [RoleInline]


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'user', 'is_leader', 'role_labels', 'joined_at')
    list_filter = ('is_leader',)
    readonly_fields = ('role_labels',)

    @admin.display(description='맡은 역할')
    def role_labels(self, obj):
        return ', '.join(r.label for r in roles_of(obj)) or '-'


@admin.register(ProjectInvitation)
class ProjectInvitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'email', 'status', 'role_labels', 'expires_at', 'invited_by')
    list_filter = ('status',)
    readonly_fields = ('token', 'role_labels')

    @admin.display(description='맡길 역할')
    def role_labels(self, obj):
        return ', '.join(r.label for r in invitation_roles(obj)) or '-'
