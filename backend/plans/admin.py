from django.contrib import admin

from .models import Checkpoint, CheckpointTask, PlanDocument


@admin.register(PlanDocument)
class PlanDocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'source_type', 'file_name', 'is_current', 'uploaded_by', 'created_at')
    list_filter = ('source_type', 'is_current')


class TaskInline(admin.TabularInline):
    model = CheckpointTask
    extra = 0
    fields = ('role', 'title', 'origin', 'state', 'assignee_member')


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'seq', 'name', 'source', 'start_at', 'end_at', 'completed_at')
    list_filter = ('source',)
    inlines = [TaskInline]
