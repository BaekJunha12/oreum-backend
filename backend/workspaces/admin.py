from django.contrib import admin

from .models import Workspace

# WorkspaceMember 는 기본키가 두 칸(workspace_id, user_id)이라 Django 관리자 화면에 따로 올릴 수 없어요.
# 대신 팀 스페이스 화면에서 멤버 목록을 읽기 전용으로 보여 줘요. 멤버 추가는 API · 초대로 해요.


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_by', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('members', 'created_at', 'updated_at')

    @admin.display(description='멤버')
    def members(self, obj):
        rows = obj.memberships.select_related('user').order_by('joined_at')
        return ', '.join(f'{m.user.name}({m.get_permission_role_display()})' for m in rows) or '-'
