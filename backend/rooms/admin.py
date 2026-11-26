from django.contrib import admin

from .models import MessageAttachment, Room, RoomMessage


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'name', 'role', 'summary_updated_at')


class AttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0


@admin.register(RoomMessage)
class RoomMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'room', 'author_user', 'body', 'created_at')
    inlines = [AttachmentInline]
