from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import User, UserIdentity


class UserCreateForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'name')


class UserEditForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'


class IdentityInline(admin.TabularInline):
    model = UserIdentity
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """관리자 화면(/admin)에서 사용자 만들기 · 비밀번호 바꾸기. 이메일이 아이디 역할이에요."""

    form = UserEditForm
    add_form = UserCreateForm
    ordering = ('id',)
    list_display = ('id', 'email', 'name', 'is_staff', 'created_at')
    search_fields = ('email', 'name')
    readonly_fields = ('last_login', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('정보', {'fields': ('name', 'profile_image_url')}),
        ('권한', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('기록', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'name', 'usable_password', 'password1', 'password2')}),
    )

    def get_inlines(self, request, obj):
        return [IdentityInline] if obj else []  # 연결된 구글 계정은 사용자를 만든 뒤에 보여요
