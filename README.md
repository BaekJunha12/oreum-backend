# Oreum(오름) — Backend

역할(디자인 · 프론트 · 백)끼리 일을 주고받는 협업 웹 **오름**의 API 서버예요.
Django 5.2 + Django REST framework. 프론트는 [A11y-Translator/frontend](https://github.com/A11y-Translator/frontend) 의 `oreum-main` 브랜치 `main2/` 폴더예요.

## 처음 실행

Python 3.10 이상이 필요해요.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
python backend\manage.py migrate
python backend\manage.py runserver
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/manage.py migrate
python backend/manage.py runserver
```

브라우저에서 http://localhost:8000/api/health 가 `{"status": "ok"}` 이면 켜진 거예요.

클론하고 한 번만 (커밋 메시지 검사 켜기, 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)):

```bash
git config core.hooksPath .githooks
git config commit.template .gitmessage
```

## 테스트

```bash
python backend/manage.py test
```

PR 을 열면 GitHub Actions 가 같은 테스트(`tests`)와 커밋 메시지 검사(`commit-convention`)를 돌려요.

## 폴더

| 경로 | 내용 |
|---|---|
| `backend/config/` | 설정, 주소 목록, CORS, 오류 모양 |
| `docs/db/` | ERD (테이블 설계) — [`docs/db/README.md`](docs/db/README.md) |

## 프론트와의 약속

프론트 `main2/README.md` 의 "백엔드 연결" 을 따라요.

- 주소는 `/api/` 아래, **끝에 `/` 가 없어요** (`/api/auth/login`). 프론트는 `.env.local` 에 `VITE_API_URL=http://localhost:8000/api` 만 적으면 붙어요.
- 오류는 4xx/5xx + `{ "message": "보여 줄 문구" }`. 문구가 그대로 화면 알림에 나와요. 입력 오류(400)는 `errors` 에 칸별 오류도 같이 줘요.
- 프론트 주소(`http://localhost:5183`)에서 credentials 를 포함해 부를 수 있게 CORS 를 열어 뒀어요 (`backend/config/cors.py`).

## 환경 변수

아무것도 안 정해도 로컬에서는 돌아가요. 배포할 때만 바꾸면 돼요.

| 변수 | 뜻 | 기본값 |
|---|---|---|
| `DJANGO_SECRET_KEY` | 비밀 키 | 로컬 전용 값 (배포 때 꼭 바꾸기) |
| `DJANGO_DEBUG` | `1` 이면 개발 모드 | `1` |
| `DJANGO_ALLOWED_HOSTS` | 접속을 받을 도메인 (쉼표로 구분) | 비어 있음 = localhost 만 |
| `CORS_ALLOWED_ORIGINS` | API 를 부를 수 있는 프론트 주소 (쉼표로 구분) | `http://localhost:5183,http://127.0.0.1:5183` |
| `DB_ENGINE` | `mysql` 이면 MySQL 사용 (`DB_NAME` · `DB_USER` · `DB_PASSWORD` · `DB_HOST` · `DB_PORT`) | 비어 있음 = SQLite |
