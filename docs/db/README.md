# DB 설계 (ERD)

- [`erd.sql`](erd.sql) — 오름 ERD 초안 v0.4 (MySQL 8). ERDCloud 에서 **가져오기 → SQL 붙여 넣기** 로 그림을 볼 수 있어요.
- 표와 칸 이름은 이 파일을 기준으로 모델(`models.py`)을 만들어요. 모델의 `db_table` · `db_column` 이 이 이름과 같아요.
- 각 앱의 `test_schema_contract` 테스트가 "ERD 의 칸이 모델에 다 있는지"를 검사해요. ERD 를 고치면 모델도 같이 고치고, 반대도 마찬가지예요.

## 묶음과 담당

| 묶음 | 표 | 앱 |
|---|---|---|
| A. 계정 · 팀 스페이스 | `users`, `user_identities`, `workspaces`, `workspace_members` | `accounts`, `workspaces` |
| B. 원정대 · 역할 · 초대 | `projects`, `project_roles`, `project_members`, `project_member_roles`, `project_invitations`, `invitation_roles` | `projects` |
| B. 기획안 · 루트 | `plan_documents`, `checkpoints`, `checkpoint_tasks` | `plans` |
| C. 넘겨주기 카드 | `handoff_cards`, `card_links`, `card_events` | `handoffs` |
| D. 방 · 대화 | `rooms`, `room_messages`, `message_attachments`, `room_reads` | (예정) |
| E. 알림 | `notifications` | `notifications` |
| F · G (2차) | GitHub 연결 · 버전 비교 · 회고 | 범위 확정 전 |

## ERD 에 없지만 코드에 있는 것

- `card_events.event_id` 는 `카드id:기록id` 로 저장해요. 프론트의 기록 id 는 카드 안에서만 겹치지 않아서예요 (알림 id 와 같은 모양).

Django 가 꼭 필요로 해서 ERD 와 조금 달라요. ERD 를 다음에 고칠 때 반영할지 정해요.

| 표 | 칸 · 규칙 | 이유 |
|---|---|---|
| `users` | `last_login`, `is_active`, `is_staff`, `is_superuser` | Django 로그인 · 관리자 화면(/admin)이 씀 |
| `users_groups`, `users_user_permissions` | (표) | Django 권한 기능이 자동으로 만듦 |
| `authtoken_token` | (표) | 로그인 토큰 (DRF 기본 기능) |
| `project_roles` | `role_key` 가 있으면 원정대 안에서 하나만 (`UQ_project_role_key`) | 디자인 · 프론트 · 백 방이 원정대마다 하나씩이라서 |
