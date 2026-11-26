# Oreum(오름) — Backend

역할(디자인 · 프론트 · 백)끼리 일을 주고받는 협업 웹 **오름**의 API 서버예요.
Django 5.2 + Django REST framework. 프론트는 [A11y-Translator/frontend](https://github.com/A11y-Translator/frontend) 의 `oreum-main` 브랜치 `main2/` 폴더예요.

## 처음 실행

Python 3.10 이상이 필요해요 (3.13 에서 확인).

**macOS (Apple Silicon 포함) / Linux**

```bash
python3 -m venv .venv                       # 가상환경 만들기
source .venv/bin/activate                   # 가상환경 켜기
pip install -r backend/requirements.txt     # Django · DRF 설치
python backend/manage.py migrate            # SQLite 표 만들기 (backend/db.sqlite3)
python backend/manage.py seed_demo          # (선택) 프론트 예시와 같은 팀 · 루트 · 카드 · 대화 · PR 넣기
python backend/manage.py runserver          # http://localhost:8000
```

**Windows (PowerShell)** — 경로만 `\` 로 바꾸고 `.venv\Scripts\activate` 로 켜요.

브라우저에서 http://localhost:8000/api/health 가 `{"status": "ok"}` 이면 켜진 거예요.
`seed_demo` 를 했다면 `minjun@example.com` / `oreum-demo-1234` 로 로그인해 볼 수 있어요 (사람 목록은 명령 출력에 나와요).

클론하고 한 번만 (커밋 메시지 검사 켜기, 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)):

```bash
git config core.hooksPath .githooks
git config commit.template .gitmessage
```

## 테스트

```bash
python backend/manage.py test                        # 전부
python backend/manage.py test versions               # 한 앱만
python backend/manage.py makemigrations --check      # 모델과 마이그레이션이 맞는지
```

PR 을 열면 GitHub Actions 가 같은 테스트(`tests`)와 커밋 메시지 검사(`commit-convention`)를 돌려요.
각 앱의 `SchemaContractTests` 가 모델과 [ERD](docs/db/erd.sql)의 칸이 같은지 검사해요.

## 폴더

| 경로 | 내용 | ERD 묶음 |
|---|---|---|
| `backend/config/` | 설정, 주소 목록, CORS, 오류 모양 | |
| `backend/accounts/` | 로그인 · Google 로그인 · 토큰 | A |
| `backend/workspaces/` | 팀 스페이스 | A |
| `backend/projects/` | 원정대 · 역할 · 초대 · 설정 · 회고 | B · G |
| `backend/plans/` | 기획 문서 · 루트(구간) · 일정 계산 · 구간 할 일 | B |
| `backend/handoffs/` | 요청 카드(요청보내기) · 주고받은 기록 | C |
| `backend/rooms/` | 역할별 방 · 대화 · 첨부 | D |
| `backend/notifications/` | 카드 기록에서 생기는 알림 | E |
| `backend/versions/` | GitHub PR 단계 · 배포 기록 · 버전 비교 코멘트 · 진행 상태 탭 | F |
| `docs/db/` | ERD (테이블 설계) — [`docs/db/README.md`](docs/db/README.md) | |

## API

모두 `/api/` 아래, 끝에 `/` 없이. 로그인 뒤에는 `Authorization: Bearer <토큰>`.
원정대가 여러 개면 `X-Project-Id: <id>` 헤더(또는 `?projectId=`)로 고르고, 없으면 가장 최근에 들어간 원정대예요.

| 묶음 | 주소 | 프론트 |
|---|---|---|
| 계정 | `POST /auth/login` · `POST /auth/google` · `POST /auth/logout` · `GET /auth/me` | `api.auth` |
| 팀 스페이스 | `GET·POST /workspaces` | `api.workspaces` |
| 원정대 | `GET·POST /projects` · `GET·PATCH /projects/<id>` · 초대 · `GET·POST /projects/<id>/retrospectives` | |
| 기획 · 일정 | `GET·PUT /plan` · `GET·PUT·DELETE /plan/document` · `GET /plan/documents` | `api.plan` |
| 기획안 파일 | `POST /files/plan` (multipart `file`) · `GET /files/plan/<id>` | `api.files.uploadPlan` |
| 루트 | `POST /route/recommend` · `GET /route` · `POST /route/start` · `POST /route/summit` | `api.route` |
| 구간 | `PATCH /checkpoints/<seq>` (날짜 · 시간) · `POST …/complete` · `POST …/reopen` · `GET·POST …/tasks` · `PATCH·DELETE /tasks/<id>` | |
| 요청 카드 | `GET·POST /requests` · `GET·PATCH·DELETE /requests/<id>` · `POST /requests/reset` (DEBUG) | `api.requests` |
| 방 | `GET /rooms` · `GET·POST /rooms/<room>/messages` · `POST /rooms/<room>/read` | `api.rooms` |
| 알림 | `GET /notifications` · `GET /notifications/unread-count` · `POST /notifications/read` | `api.notifications` |
| GitHub | `GET /github` · `POST /github/repos` · `GET·POST /github/pulls` · `PATCH /github/pulls/<id>` · `POST /github/webhook` | (상태 탭) |
| 버전 비교 | `GET·POST /versions` · `GET /versions/compare` · `GET·POST /versions/<id>/comments` · `PATCH·DELETE /compare-comments/<id>` · `POST /compare-comments/<id>/request` | (비교 탭) |
| 진행 상태 | `GET /status` | (상태 탭) |

각 `views.py` 맨 위에 주소마다 받는 값 · 돌려주는 값을 적어 뒀어요.

### 팀 변경 11/26 반영

| 바뀐 것 | 서버에서 |
|---|---|
| 일정을 시간 단위로 · "n시간 남음" | `scheduleUnit = hour` · 구간 `startAt`/`endAt` 이 DATETIME (ERD v0.5) · `remaining.text` |
| 일 단위도 날짜 · 시간 수정 | `PATCH /checkpoints/<seq>` `{ startAt, endAt }` (리더) |
| 기획 문서 수정 · 빈 상태 | `PUT /plan/document` `{ text }` · 없으면 `message: "아직 기획 문서가 없어요"` |
| 다른 역할 방에는 대화 금지 | 403 `room_read_only` + "요청보내기로 보내 주세요" · `GET /rooms` 의 `canWrite` |
| 넘겨주기 → 요청보내기 | 요청 카드 상태표를 서버가 직접 적용 (`invalid_transition` · `maker_only` · `requester_only`) |
| 버전 비교 · 상태 탭 | `versions` 앱: PR 단계, 배포되면 연결 카드 자동 전달, 화면 위 코멘트 → 요청 카드 |

### 구간 일정 나누기

프론트 `planStore.checkpointRanges` 와 같은 규칙이고 단위만 일 · 시간 둘 다 돼요 (`backend/plans/schedule.py`).

$$S = \text{마감} - \text{시작},\quad L = \max(1, \operatorname{round}(0.36\,S)),\quad \text{step} = \frac{S - L}{n - 1}$$

$$\text{구간}_i = \big[\,\text{시작} + \operatorname{round}(i\cdot\text{step}),\ \text{시작} + \operatorname{round}(i\cdot\text{step} + L)\,\big]\quad(\text{마지막 구간은 마감에 끝남})$$

예) 11/19 시작 · 12/03 마감 · 4개 → S = 14, L = 5, step = 3 → 11/19–11/24, 11/22–11/27, 11/25–11/30, 11/28–12/03.
남은 시간: 일 단위는 달력 날짜 차이("n일 남음 · 오늘 마감 · n일 지남"), 시간 단위는 ⌈(마감 − 지금) / 1시간⌉ ("n시간 남음").

## 프론트와의 약속

프론트 `main2/README.md` 의 "백엔드 연결" 을 따라요.

- 주소는 `/api/` 아래, **끝에 `/` 가 없어요** (`/api/auth/login`). 프론트는 `.env.local` 에 `VITE_API_URL=http://localhost:8000/api` 만 적으면 붙어요.
- 오류는 4xx/5xx + `{ "message": "보여 줄 문구", "code": "..." }`. 문구가 그대로 화면 알림에 나와요. 입력 오류(400)는 `errors` 에 칸별 오류도 같이 줘요.
- 카드 · 기록 · 메시지 id 는 프론트가 만들어 보내면 그대로 써요 (겹치면 409).
- 프론트 주소(`http://localhost:5183`)에서 credentials 를 포함해 부를 수 있게 CORS 를 열어 뒀어요 (`backend/config/cors.py`, `X-Project-Id` 헤더 포함).

## 환경 변수

아무것도 안 정해도 로컬에서는 돌아가요. 배포할 때만 바꾸면 돼요.

| 변수 | 뜻 | 기본값 |
|---|---|---|
| `DJANGO_SECRET_KEY` | 비밀 키 | 로컬 전용 값 (배포 때 꼭 바꾸기) |
| `DJANGO_DEBUG` | `1` 이면 개발 모드 | `1` |
| `DJANGO_ALLOWED_HOSTS` | 접속을 받을 도메인 (쉼표로 구분) | 비어 있음 = localhost 만 |
| `CORS_ALLOWED_ORIGINS` | API 를 부를 수 있는 프론트 주소 (쉼표로 구분) | `http://localhost:5183,http://127.0.0.1:5183` |
| `DB_ENGINE` | `mysql` 이면 MySQL 사용 (`DB_NAME` · `DB_USER` · `DB_PASSWORD` · `DB_HOST` · `DB_PORT`) | 비어 있음 = SQLite |
| `MEDIA_ROOT` | 올린 기획안 파일을 두는 폴더 | `backend/media/` |
| `GITHUB_WEBHOOK_SECRET` | GitHub 웹훅 서명 비밀값. 있으면 `POST /api/github/webhook` 이 켜져요 | 비어 있음 = 꺼짐 |
