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

예시 사용자 · 원정대 넣기 (프론트 예시 화면과 같은 사람들, 여러 번 해도 한 벌만 생김):

```bash
python backend/manage.py seed_demo
```

`hyeseung@example.com` / `oreum-demo-1234` 처럼 로그인할 수 있어요 (명령이 목록을 보여 줘요).
관리자 화면(http://localhost:8000/admin)을 쓰려면 `python backend/manage.py createsuperuser` 로 계정을 만들어요.

클론하고 한 번만 (커밋 메시지 검사 켜기, 자세한 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)):

```bash
git config core.hooksPath .githooks
git config commit.template .gitmessage
```

## 테스트

```bash
python backend/manage.py test            # 전부
python backend/manage.py test projects   # 한 앱만
```

PR 을 열면 GitHub Actions 가 같은 테스트(`tests`)와 커밋 메시지 검사(`commit-convention`)를 돌려요.

## 폴더

| 경로 | 내용 |
|---|---|
| `backend/config/` | 설정, 주소 목록, CORS, 오류 모양, ERD 대조 테스트 도우미 |
| `backend/accounts/` | 사용자, 로그인 (Bearer 토큰) |
| `backend/workspaces/` | 팀 스페이스, 팀 스페이스 멤버 |
| `backend/projects/` | 원정대, 역할, 원정대원, 초대, `seed_demo` 명령 |
| `backend/handoffs/` | 넘겨주기 카드(요청), 카드 링크, 주고받은 기록 (C) |
| `backend/plans/` | 기획안 파일 올리기, 루트의 구간(체크포인트), 구간 할 일 (B 진행 중) |
| `docs/db/` | ERD (테이블 설계) — [`docs/db/README.md`](docs/db/README.md) |

## 프론트와의 약속

프론트 `main2/README.md` 의 "백엔드 연결" 을 따라요.

- 주소는 `/api/` 아래, **끝에 `/` 가 없어요** (`/api/auth/login`). 프론트는 `.env.local` 에 `VITE_API_URL=http://localhost:8000/api` 만 적으면 붙어요.
- 오류는 4xx/5xx + `{ "message": "보여 줄 문구" }`. 문구가 그대로 화면 알림에 나와요. 입력 오류(400)는 `errors` 에 칸별 오류도 같이 줘요.
- 프론트 주소(`http://localhost:5183`)에서 credentials 를 포함해 부를 수 있게 CORS 를 열어 뒀어요 (`backend/config/cors.py`).
- 로그인하면 `{ token, user }` 를 주고, 그 뒤 요청은 `Authorization: Bearer <token>` 으로 와요. 토큰이 없거나 틀리면 401 → 프론트가 로그아웃해요.
- id 는 글자(`"12"`)로, JSON 칸 이름은 프론트처럼 camelCase(`deadlineAt`)로 보내요.

### 프론트 붙여 보기

1. 서버: `python backend/manage.py seed_demo` → `python backend/manage.py runserver`
2. 프론트 `main2/.env.local` 에 `VITE_API_URL=http://localhost:8000/api` → `npm run dev` 다시 켜기
3. http://localhost:5183 에서 `hyeseung@example.com` / `oreum-demo-1234` 로 로그인

지금은 로그인 · 내 정보 · 팀 스페이스만 서버 값이에요. 일정 · 카드 · 방 · 알림은 아래 "다음에 만들 API" 가 생기면 붙어요. 그 전에는 프론트에 `일정 불러오기 실패 — 아직 없는 API 예요 (GET /api/plan)` 같은 알림이 떠요 (없는 `/api/` 주소는 이렇게 답해요).

## API

모두 `/api` 뒤에 붙어요. ✅ = 만듦, 나머지는 프론트(main2) 가 부르는데 아직 없는 것.

### 계정 · 팀 스페이스 (A)

| | 주소 | 요청 → 응답 | 비고 |
|---|---|---|---|
| ✅ | `POST /auth/login` | `{ email, password }` → `{ token, user }` | 틀리면 400 `이메일 또는 비밀번호가 틀렸어요` |
| ✅ | `POST /auth/register` | `{ email, password, name }` → 201 `{ token, user }` | 프론트 화면은 아직 없음 (개발용) |
| ✅ | `POST /auth/google` | `{ credential }` → 501 | 구글 로그인 창이 붙으면 만들어요 |
| ✅ | `POST /auth/logout` | → 204 | 토큰을 지워요 (모든 기기에서 로그아웃) |
| ✅ | `GET /auth/me` | → `{ id, name, email, role }` | `role` = 지금 원정대에서 맡은 첫 기본 역할 |
| ✅ | `GET /workspaces` | → `[{ id, name }]` | 내가 들어가 있는 것만, 먼저 들어간 순서 |
| ✅ | `POST /workspaces` | `{ name }` → 201 `{ id, name }` | 만든 사람 = 주인(owner) |

### 원정대 · 초대 (A) — 프론트 화면이 아직 없어 모양은 임시

| | 주소 | 요청 → 응답 | 비고 |
|---|---|---|---|
| ✅ | `GET /projects` | → 내 원정대 목록 (`current: true` = 지금 원정대) | |
| ✅ | `POST /projects` | `{ name, deadlineAt, scheduleUnit?, workspaceId?, roles?: [{ label, people, role? }], myRoles? }` → 201 상세 | 만든 사람 = 리더. `roles` 가 없으면 디자인 · 프론트 · 백 1명씩 |
| ✅ | `GET /projects/<id>` | → 상세 (`roles`, `members`, 리더에게만 `invitations`) | 원정대원이 아니면 404 |
| ✅ | `POST /projects/<id>/invitations` | `{ email?, roleIds? }` → 201 `{ id, token, status, roles, expiresAt, … }` | 리더만. `email` 이 없으면 링크 초대. 7일 동안, 한 번 쓰면 끝 |
| ✅ | `POST /projects/<id>/invitations/<invId>/revoke` | → 초대 | 리더만, 초대 대기 중인 것만 |
| ✅ | `GET /invitations/<token>` | → `{ project, invitedBy, roles, status, expiresAt }` | 로그인 전에도 볼 수 있어요 |
| ✅ | `POST /invitations/<token>/accept` | → `{ project, member }` | 원정대원이 되고 초대의 역할을 맡아요 |


### 넘겨주기 카드 (C)

| | 주소 | 요청 → 응답 | 비고 |
|---|---|---|---|
| ✅ | `GET /requests` | → `HandoffCard[]` | 지금 원정대의 카드. 원정대가 없으면 `[]` |
| ✅ | `POST /requests` | `HandoffCard` → 201 `HandoffCard` | id 는 프론트가 만들어요. 같은 id 로 다시 보내면 만든 카드를 그대로 돌려줘요 (다른 원정대가 쓴 id 면 409 `card_id_taken`) |
| ✅ | `PATCH /requests/<id>` | `{ action, card }` → `HandoffCard` | `action` 이 지금 상태에서 할 수 있는 일이고 `card.status` 가 그 결과일 때만 저장해요. 아니면 409 `card_conflict` (다른 사람이 먼저 바꿈). 기록(history)은 새 id 만 더해지고 이미 있는 기록은 안 바뀌어요 |

상태가 바뀌는 규칙 (`handoffs/services.py` 의 `TRANSITIONS`):

| 한 일 | 할 수 있는 상태 | 끝난 뒤 |
|---|---|---|
| `accept` · `acceptProposed` | requested | accepted |
| `propose` | requested | 그대로 |
| `deliver` | requested · accepted | delivered |
| `fix` | delivered | accepted |
| `confirm` | delivered | confirmed |
| `block` / `unblock` | accepted (안 막힘) / 막힘 | 그대로 |
| `comment` | 언제나 | 그대로 |

### 기획안 · 루트 (B)

| | 주소 | 요청 → 응답 | 비고 |
|---|---|---|---|
| ✅ | `POST /files/plan` | multipart(칸 이름 `file`) → 201 `{ id, name, size, type, pages, url? }` | 리더만 (원정대가 아직 없으면 만들어 줘요). pdf · md · txt · 이미지, 20MB 까지. 새로 올리면 이전 기획안은 `is_current = false`. `pages` 는 아직 `null`, `url` 은 안 줘요 (파일은 `backend/media/` 에 저장, git 에는 안 올라가요) |


### 다음에 만들 API (프론트가 이미 부르는 것)

| 주소 | 담당 (안) | 프론트 타입 |
|---|---|---|
| `GET` · `PUT /plan` | B | `Plan { unit, date, time, roles, checkpoints }` |
| `POST /route/recommend` | B | `RouteRecommendInput` → `RouteRecommendation` |
| `GET` · `POST /rooms/:room/messages` | C | `RoomMessage` |
| `GET /notifications`, `POST /notifications/read` | C | `Notification`, `MarkReadInput` |

## 다른 앱이 A 를 쓰는 법

B · C 는 원정대 표를 직접 고치지 말고 `projects/services.py` 함수를 불러요. 테스트 준비는 `projects/testing.py`.

```python
from projects.services import current_project, membership, role_keys

project = current_project(request.user)          # 지금 원정대 (없으면 None)
member = membership(request.user, project)       # 원정대원 행 (없으면 None → 403/404)
role_keys(member)                                # ['design'] — 카드의 fromRole · 방 이름과 같은 값
```

```python
from projects.testing import add_to, api_as, make_project

project, leader = make_project()                       # 디자인 · 프론트 · 백 1명씩, 리더 = 디자인
front = add_to(project, 'front@example.com', 'front')  # 프론트 원정대원
api_as(front.user).get('/api/plan')                    # Bearer 토큰을 붙인 클라이언트
```

**지금 원정대** — 프론트는 `GET /plan` 처럼 원정대 id 없이 불러요. 그래서 서버가 **가장 최근에 들어간 원정대**를 지금 원정대로 봐요 (`current_project`). 원정대를 고르는 화면이 생기면 이 함수만 바꾸면 돼요.

## 다른 앱이 B 를 쓰는 법

C 도 구간 표를 직접 뒤지지 말고 `plans/services.py` 함수를 불러요. 구간(`Checkpoint`)은 원정대마다 0번(베이스 캠프)부터 이어지는 번호 `seq` 가 있어요.

```python
from plans.models import Checkpoint
from plans.services import checkpoint_by_seq, current_checkpoint

cp = current_checkpoint(project)       # 지금 구간 — 카드 · 메시지에 구간을 안 골랐을 때 기본값 (항상 하나)
cp = checkpoint_by_seq(project, 2)     # 프론트가 보낸 구간 번호 → 구간 (없으면 None)
cp.seq                                 # 프론트로 내보낼 때 쓰는 번호 (HandoffCard.checkpoint)
```

- 프론트의 카드 · 메시지는 구간을 id 가 아니라 **번호**로 가리켜요. 저장할 때는 `checkpoint_by_seq` 로 구간을 찾아 FK 에 넣고, 응답에는 `seq` 를 내보내요.
- 지금 구간 = 안 끝난 화면 구간 중 번호가 가장 작은 것 (전부 끝났으면 마지막, 화면 구간이 없으면 베이스 캠프).
- 구간을 지우면 카드 · 메시지의 `checkpoint_id` 는 비워져요 (`ON DELETE SET NULL`). 일정 저장(B-04)은 구간을 지우지 않고 이름만 바꾸도록 만들 예정이에요.

## 팀이 정할 것

| 무엇 | 지금 코드 | 바꾸면 고칠 곳 |
|---|---|---|
| 팀 스페이스 : 원정대 = 1 : 1 또는 1 : N | 1 : N (ERD 그대로) | `projects` 모델 · `current_project` |
| 원정대가 없는 사용자의 `user.role` | `design` 으로 보냄 (프론트가 세 값 말고는 로그아웃시켜서) | `accounts/payloads.py` 의 `FALLBACK_ROLE` |
| 사람 · 날짜를 이름 · 화면 글자 대신 id · ISO 날짜로 주고받기 | 원정대 API 는 id · ISO. 카드 · 방은 아직 없음 | 프론트 `types.ts` 와 같이 |
| 링크 초대를 여러 명이 쓸지 | 한 번 쓰면 끝 (ERD 의 `accepted_by` 가 한 칸) | `accept_invitation` |
| 초대는 리더만? | 리더만 | `_require_leader` |

## 브랜치

`main` ← `development` ← 작업 브랜치(`feat/…`, `fix/…`). 작업 브랜치에서 `development` 로 PR 을 열고, 테스트 · 커밋 검사가 초록불이면 머지해요.

## 환경 변수

아무것도 안 정해도 로컬에서는 돌아가요. 배포할 때만 바꾸면 돼요.

| 변수 | 뜻 | 기본값 |
|---|---|---|
| `DJANGO_SECRET_KEY` | 비밀 키 | 로컬 전용 값 (배포 때 꼭 바꾸기) |
| `DJANGO_DEBUG` | `1` 이면 개발 모드 | `1` |
| `DJANGO_ALLOWED_HOSTS` | 접속을 받을 도메인 (쉼표로 구분) | 비어 있음 = localhost 만 |
| `CORS_ALLOWED_ORIGINS` | API 를 부를 수 있는 프론트 주소 (쉼표로 구분) | `http://localhost:5183,http://127.0.0.1:5183` |
| `DB_ENGINE` | `mysql` 이면 MySQL 사용 (`DB_NAME` · `DB_USER` · `DB_PASSWORD` · `DB_HOST` · `DB_PORT`) | 비어 있음 = SQLite |
