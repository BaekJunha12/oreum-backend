from django.contrib import admin

from .models import Room, RoomMessage


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'name', 'role', 'created_at')


@admin.register(RoomMessage)
class RoomMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'room', 'author_user', 'author_role', 'is_notice', 'created_at')
    search_fields = ('id', 'body')
