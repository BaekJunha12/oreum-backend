"""
Oreum(오름) 백엔드 설정.

아무 설정 없이 켜도 로컬에서 돌아가도록 기본값을 넣어 두었어요.
배포할 때 바꿔야 하는 값은 환경 변수로 받아요 (README의 "환경 변수" 표).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=''):
    """'a,b,c' 형태의 환경 변수를 리스트로 (빈 칸은 버림)."""
    return [v.strip() for v in os.environ.get(name, default).split(',') if v.strip()]


# 배포할 때는 반드시 DJANGO_SECRET_KEY 를 따로 정해 주세요.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-local-only-do-not-use-in-production')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS')  # 비어 있고 DEBUG 이면 localhost · 127.0.0.1 만 허용


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'accounts',
]

MIDDLEWARE = [
    'config.cors.CorsMiddleware',  # 맨 앞: 브라우저의 사전 확인(OPTIONS)에 바로 답함
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# 데이터베이스: 기본은 SQLite 파일(backend/db.sqlite3). DB_ENGINE=mysql 이면 MySQL.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
if os.environ.get('DB_ENGINE') == 'mysql':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'oreum'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'pw'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# 한국어 · 한국 시간. DB에는 UTC로 저장되고, 화면에 보일 때 한국 시간으로 바뀌어요.
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
TEST_RUNNER = 'config.test_runner.BackendDiscoverRunner'  # 저장소 맨 위에서 실행해도 테스트를 찾게
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# 프론트(main2)가 부르는 주소는 끝에 / 가 없어요 (/auth/login). 주소도 그대로 맞춥니다.
APPEND_SLASH = False


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'accounts.authentication.BearerTokenAuthentication',  # 프론트: Authorization: Bearer <토큰>
        'rest_framework.authentication.SessionAuthentication',  # /admin 로그인한 채 브라우저로 /api 를 열어 볼 때
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    # 오류는 항상 { "message": "보여 줄 문구" } — 프론트가 이 문구를 그대로 알림에 띄워요
    'EXCEPTION_HANDLER': 'config.errors.exception_handler',
}

# 이 API를 브라우저에서 불러도 되는 프론트 주소 (config/cors.py)
CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS', 'http://localhost:5183,http://127.0.0.1:5183')
