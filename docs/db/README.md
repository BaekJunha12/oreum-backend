# DB 설계 (ERD)

- [`erd.sql`](erd.sql) — 오름 ERD 초안 v0.5 (MySQL 8). ERDCloud 에서 **가져오기 → SQL 붙여 넣기** 로 그림을 볼 수 있어요.
- 표와 칸 이름은 이 파일을 기준으로 모델(`models.py`)을 만들어요. 모델의 `db_table` · `db_column` 이 이 이름과 같아요.
- 각 앱의 `test_schema_contract` 테스트가 "ERD 의 칸이 모델에 다 있는지"를 검사해요. ERD 를 고치면 모델도 같이 고치고, 반대도 마찬가지예요.

## 묶음과 담당

| 묶음 | 표 | 앱 |
|---|---|---|
| A. 계정 · 팀 스페이스 | `users`, `user_identities`, `workspaces`, `workspace_members` | `accounts`, `workspaces` |
| B. 원정대 · 역할 · 초대 | `projects`, `project_roles`, `project_members`, `project_member_roles`, `project_invitations`, `invitation_roles` | `projects` |
| B. 기획안 · 루트 | `plan_documents`, `checkpoints`, `checkpoint_tasks` | `plans` |
| C. 요청 카드 (요청보내기) | `handoff_cards`, `card_links`, `card_events` | `handoffs` |
| D. 방 · 대화 | `rooms`, `room_messages`, `message_attachments`, `room_reads` | `rooms` |
| E. 알림 | `notifications` | `notifications` |
| F. GitHub 연결 · 버전 비교 | `github_repositories`, `github_pull_requests`, `app_versions`, `compare_comments` | `versions` |
| G. 회고 | `retrospectives` | `projects` |

## 바뀐 것

| 버전 | 바뀐 것 | 이유 |
|---|---|---|
| v0.5 | `checkpoints.start_date` · `end_date` (DATE) → `start_at` · `end_at` (DATETIME) | 팀 변경 11/26: 시간 단위 일정, 화면에 "n시간 남음" |

## ERD 에 없지만 코드에 있는 것

Django 가 꼭 필요로 해서 ERD 와 조금 달라요. ERD 를 다음에 고칠 때 반영할지 정해요.

| 표 | 칸 · 규칙 | 이유 |
|---|---|---|
| `users` | `last_login`, `is_active`, `is_staff`, `is_superuser` | Django 로그인 · 관리자 화면(/admin)이 씀 |
| `users_groups`, `users_user_permissions` | (표) | Django 권한 기능이 자동으로 만듦 |
| `authtoken_token` | (표) | 로그인 토큰 (DRF 기본 기능) |
| `project_roles` | `role_key` 가 있으면 원정대 안에서 하나만 (`UQ_project_role_key`) | 디자인 · 프론트 · 백 방이 원정대마다 하나씩이라서 |
| `plan_documents` | 원정대마다 지금 쓰는 문서(`is_current`)는 하나만 (`UQ_plan_document_current`, 조건부 UNIQUE) | MySQL 은 조건부 UNIQUE 가 없어서 앱에서도 같이 검사 |
| `rooms` | 전체 방(`role_id` 없음)도 원정대마다 하나만 (`UQ_room_all`, 조건부 UNIQUE) | NULL 은 UNIQUE 에 안 걸려서 |
| `handoff_cards` · `github_pull_requests` · `app_versions` · `compare_comments` | 상태 · 단계 · 환경 · 종류 칸에 CHECK (`CK_card_status`, `CK_pr_stage`, `CK_version_environment`, `CK_compare_comment_kind` …) | 잘못된 값이 DB 에 들어가지 않게 |
