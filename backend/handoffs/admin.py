from django.contrib import admin

from .models import CardEvent, CardLink, HandoffCard


class LinkInline(admin.TabularInline):
    model = CardLink
    extra = 0


class EventInline(admin.TabularInline):
    model = CardEvent
    extra = 0
    fields = ('id', 'kind', 'author_user', 'author_role', 'text', 'created_at')


@admin.register(HandoffCard)
class HandoffCardAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'title', 'from_role', 'to_role', 'status', 'due_label', 'updated_at')
    list_filter = ('status', 'origin')
    search_fields = ('id', 'title')
    inlines = [LinkInline, EventInline]
