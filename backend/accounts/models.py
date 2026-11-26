"""A. 계정 — users, user_identities (docs/db/erd.sql)."""
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """User.objects.create_user(email, password, name=...) — 다른 앱 테스트도 이걸로 사용자를 만들어요."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('email is required')
        extra.setdefault('name', email.split('@')[0])
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # 구글 로그인만 쓰는 사용자
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """사용자. 이메일로 로그인해요 (아이디 칸 없음)."""

    id = models.BigAutoField(primary_key=True, db_column='user_id')
    email = models.EmailField('로그인 이메일', max_length=255, unique=True)
    password = models.CharField('비밀번호 해시', max_length=255, null=True, blank=True, db_column='password_hash')
    name = models.CharField('표시 이름', max_length=50)
    profile_image_url = models.CharField('프로필 사진', max_length=500, null=True, blank=True)
    # 아래 둘은 ERD 에 없지만 Django 로그인 · 관리자 화면에 필요해요 (docs/db/README.md)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()
    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'users'
        verbose_name = verbose_name_plural = '사용자'

    def __str__(self):
        return f'{self.name} <{self.email}>'


class UserIdentity(models.Model):
    """구글 · 학교 계정으로 로그인한 사용자를 우리 사용자와 이어 줌."""

    PROVIDERS = [('google', '구글'), ('school_sso', '학교 계정')]

    id = models.BigAutoField(primary_key=True, db_column='identity_id')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='identities')
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    provider_user_id = models.CharField('제공자 쪽 고유값', max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_identities'
        verbose_name = verbose_name_plural = '외부 계정 연결'
        constraints = [models.UniqueConstraint(fields=['provider', 'provider_user_id'], name='UQ_identity')]
