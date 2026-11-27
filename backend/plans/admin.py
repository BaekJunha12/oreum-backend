from django.contrib import admin

from .models import Checkpoint


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'seq', 'name', 'source', 'arrived_at', 'completed_at')
    list_filter = ('source',)
    ordering = ('project', 'seq')
