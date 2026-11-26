-- =====================================================================
-- Oreum(오름) ERD 초안 v0.5 — MySQL 8 (ERDCloud "가져오기"에 붙여 넣는 용도)
-- 근거: Figma "11/18 추가회의" 페이지(최종 3 · 다듬음, 원정대 구성·초대 플로우, 요청 흐름, 루트 설정 규칙, 역할별 협업 웹 기획안 §1~§6)
-- 용어: 기획안의 "시퀀스" = 최신 화면의 "구간(체크포인트)" → checkpoints 표 하나로 처리
--       프론트 A11y-Translator/frontend 의 oreum-main 브랜치 main2/ (api/types.ts, data/*Store.ts, README)
-- 표기: 테이블·칸 이름은 snake_case, COMMENT 는 한국어 논리명/설명
-- 1차(지금 프론트가 쓰는 것) = A~E, 2차(화면만 있고 확정 전) = F~G
-- 프론트가 id 를 만들어 보내는 것(카드 · 기록 · 메시지)은 VARCHAR(64) 기본키
-- 외래키는 맨 아래 ALTER TABLE 로 모아 둠 (가져오기 순서 문제 방지)
-- v0.5 (팀 변경 11/26): 시간 단위 일정 — checkpoints.start_date · end_date(DATE) → start_at · end_at(DATETIME)
-- =====================================================================

-- ---------------------------------------------------------------------
-- A. 계정 · 팀 스페이스
-- ---------------------------------------------------------------------

CREATE TABLE `users` (
  `user_id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '사용자 ID',
  `email`             VARCHAR(255) NOT NULL COMMENT '로그인 이메일(소문자)',
  `password_hash`     VARCHAR(255) NULL     COMMENT '비밀번호 해시(구글·학교 계정 전용이면 NULL)',
  `name`              VARCHAR(50)  NOT NULL COMMENT '표시 이름',
  `profile_image_url` VARCHAR(500) NULL     COMMENT '프로필 사진',
  `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '가입일시',
  `updated_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `UQ_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='사용자';

CREATE TABLE `user_identities` (
  `identity_id`      BIGINT       NOT NULL AUTO_INCREMENT COMMENT '외부 로그인 연결 ID',
  `user_id`          BIGINT       NOT NULL COMMENT '사용자',
  `provider`         VARCHAR(20)  NOT NULL COMMENT 'google | school_sso',
  `provider_user_id` VARCHAR(255) NOT NULL COMMENT '제공자 쪽 고유값(구글 sub 등)',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '연결일시',
  PRIMARY KEY (`identity_id`),
  UNIQUE KEY `UQ_identity` (`provider`, `provider_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='외부 계정 로그인(구글·학교)';

CREATE TABLE `workspaces` (
  `workspace_id` BIGINT       NOT NULL AUTO_INCREMENT COMMENT '팀 스페이스 ID',
  `name`         VARCHAR(100) NOT NULL COMMENT '팀 스페이스 이름',
  `image_url`    VARCHAR(500) NULL     COMMENT '팀 스페이스 사진',
  `created_by`   BIGINT       NOT NULL COMMENT '만든 사람',
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
  PRIMARY KEY (`workspace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='팀 스페이스(사이드바 맨 위)';

CREATE TABLE `workspace_members` (
  `workspace_id`    BIGINT      NOT NULL COMMENT '팀 스페이스',
  `user_id`         BIGINT      NOT NULL COMMENT '사용자',
  `permission_role` VARCHAR(10) NOT NULL DEFAULT 'member' COMMENT 'owner | admin | member',
  `joined_at`       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '참여일시',
  PRIMARY KEY (`workspace_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='팀 스페이스 멤버';

-- ---------------------------------------------------------------------
-- B. 원정대(프로젝트) · 기획안 · 역할 · 초대 · 루트(체크포인트)
-- ---------------------------------------------------------------------

CREATE TABLE `projects` (
  `project_id`             BIGINT       NOT NULL AUTO_INCREMENT COMMENT '원정대(프로젝트) ID',
  `workspace_id`           BIGINT       NOT NULL COMMENT '속한 팀 스페이스',
  `name`                   VARCHAR(100) NOT NULL COMMENT '프로젝트 이름(예: 캠퍼스 앱)',
  `deadline_at`            DATETIME     NOT NULL COMMENT '정상 · 최종 마감(예: 2026-12-03 18:00)',
  `schedule_unit`          VARCHAR(10)  NOT NULL DEFAULT 'day' COMMENT '일정 단위: day | hour',
  `status`                 VARCHAR(10)  NOT NULL DEFAULT 'planning' COMMENT 'planning(루트 만드는 중) | climbing(출발함) | completed(정상 도착)',
  `route_source_signature` VARCHAR(255) NULL     COMMENT '루트를 만든 기획안 표시(같은 기획안이면 루트를 다시 만들지 않음)',
  `recommend_all_tasks`    BOOLEAN      NOT NULL DEFAULT FALSE COMMENT '설정 "전체 할 일 받기": TRUE 면 출발할 때 모든 구간의 할 일을 한 번에 추천',
  `started_at`             DATETIME     NULL     COMMENT '"이 루트로 출발하기" 누른 시각',
  `completed_at`           DATETIME     NULL     COMMENT '정상 도착 시각',
  `created_by`             BIGINT       NOT NULL COMMENT '만든 사람(리더)',
  `created_at`             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  `updated_at`             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
  PRIMARY KEY (`project_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='원정대(프로젝트) · 시작하기의 일정';

CREATE TABLE `plan_documents` (
  `plan_document_id` BIGINT       NOT NULL AUTO_INCREMENT COMMENT '기획안 ID',
  `project_id`       BIGINT       NOT NULL COMMENT '원정대',
  `source_type`      VARCHAR(10)  NOT NULL COMMENT '넣은 방법: file | link | text',
  `file_name`        VARCHAR(255) NULL     COMMENT '파일 이름(캠퍼스앱_기획안_v3.pdf)',
  `file_size`        BIGINT       NULL     COMMENT '파일 크기(바이트)',
  `mime_type`        VARCHAR(100) NULL     COMMENT 'application/pdf, text/markdown …',
  `page_count`       INT          NULL     COMMENT '쪽수(모르면 NULL)',
  `storage_url`      VARCHAR(700) NULL     COMMENT '올린 파일 저장 위치',
  `link_url`         VARCHAR(700) NULL     COMMENT '링크로 넣었을 때 주소',
  `text_content`     MEDIUMTEXT   NULL     COMMENT '직접 입력했을 때 본문 / 파일에서 뽑은 글자',
  `is_current`       BOOLEAN      NOT NULL DEFAULT TRUE COMMENT '지금 쓰는 기획안인지(바꾸기 하면 이전 것은 FALSE)',
  `uploaded_by`      BIGINT       NOT NULL COMMENT '올린 사람',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '올린 일시',
  PRIMARY KEY (`plan_document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='기획안(파일 · 링크 · 직접 입력)';

CREATE TABLE `project_roles` (
  `role_id`    BIGINT      NOT NULL AUTO_INCREMENT COMMENT '역할 자리 ID',
  `project_id` BIGINT      NOT NULL COMMENT '원정대',
  `role_key`   VARCHAR(10) NULL     COMMENT '기본 역할이면 design | front | back, 직접 추가한 역할(기획·QA)은 NULL',
  `label`      VARCHAR(30) NOT NULL COMMENT '화면 이름(디자인 · 프론트 · 백 · 기획 …)',
  `headcount`  INT         NOT NULL DEFAULT 1 COMMENT '필요 인원(디자인 2명)',
  `sort_order` INT         NOT NULL DEFAULT 0 COMMENT '보여 줄 순서',
  `created_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  PRIMARY KEY (`role_id`),
  UNIQUE KEY `UQ_project_role_label` (`project_id`, `label`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='역할 자리(AI가 기획안에서 찾거나 직접 추가)';

CREATE TABLE `project_members` (
  `member_id`  BIGINT   NOT NULL AUTO_INCREMENT COMMENT '원정대원 ID',
  `project_id` BIGINT   NOT NULL COMMENT '원정대',
  `user_id`    BIGINT   NOT NULL COMMENT '사용자',
  `is_leader`  BOOLEAN  NOT NULL DEFAULT FALSE COMMENT '리더 여부("나 · 리더")',
  `joined_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '참여일시',
  PRIMARY KEY (`member_id`),
  UNIQUE KEY `UQ_project_member` (`project_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='원정대원';

CREATE TABLE `project_member_roles` (
  `member_id` BIGINT NOT NULL COMMENT '원정대원',
  `role_id`   BIGINT NOT NULL COMMENT '맡은 역할(여러 개 가능)',
  PRIMARY KEY (`member_id`, `role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='원정대원 ↔ 역할';

CREATE TABLE `project_invitations` (
  `invitation_id` BIGINT       NOT NULL AUTO_INCREMENT COMMENT '초대 ID',
  `project_id`    BIGINT       NOT NULL COMMENT '원정대',
  `email`         VARCHAR(255) NULL     COMMENT '초대받는 이메일(링크 초대면 NULL)',
  `token`         CHAR(64)     NOT NULL COMMENT '초대 링크 토큰',
  `invited_by`    BIGINT       NOT NULL COMMENT '초대한 사람',
  `status`        VARCHAR(10)  NOT NULL DEFAULT 'pending' COMMENT 'pending(초대 대기) | accepted | revoked | expired',
  `accepted_by`   BIGINT       NULL     COMMENT '수락한 사용자',
  `expires_at`    DATETIME     NOT NULL COMMENT '만료(링크는 7일)',
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '초대일시',
  PRIMARY KEY (`invitation_id`),
  UNIQUE KEY `UQ_invitation_token` (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='원정대 초대(이메일 · 링크)';

CREATE TABLE `invitation_roles` (
  `invitation_id` BIGINT NOT NULL COMMENT '초대',
  `role_id`       BIGINT NOT NULL COMMENT '들어오면 배정할 역할(여러 개 가능)',
  PRIMARY KEY (`invitation_id`, `role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='초대 ↔ 역할';

CREATE TABLE `checkpoints` (
  `checkpoint_id` BIGINT       NOT NULL AUTO_INCREMENT COMMENT '체크포인트(구간) ID',
  `project_id`    BIGINT       NOT NULL COMMENT '원정대',
  `seq`           INT          NOT NULL COMMENT '순서. 0 = 베이스캠프(항상 있음, 공통 작업), 1~ = 화면 구간(의존성 순서). 정상은 projects.deadline_at',
  `name`          VARCHAR(100) NOT NULL COMMENT '구간 이름(베이스캠프 · 로그인 · 메인 피드 …)',
  `start_at`      DATETIME     NULL     COMMENT '구간 시작 시각(일 단위면 그날 0시, 시간 단위면 정시) — v0.5',
  `end_at`        DATETIME     NULL     COMMENT '목표 완성 시각(구간끼리 겹쳐도 됨, "n일 남음" · "n시간 남음" 계산) — v0.5',
  `source`        VARCHAR(10)  NOT NULL DEFAULT 'plan' COMMENT 'plan(기획안의 MVP 화면) | ai(화면 목록이 없어 AI가 추론 → AI 추천 태그) | manual(직접 추가)',
  `order_reason`  VARCHAR(500) NULL     COMMENT '기획안 순서와 다르게 놓았을 때 그 이유(화면에 보여 줌)',
  `arrived_at`    DATETIME     NULL     COMMENT '이 구간에 도착한 시각(이때 앞 구간 막힘·지연을 반영해 할 일 추천)',
  `completed_at`  DATETIME     NULL     COMMENT '구간 완료(그 화면이 디자인·프론트·백 모두 끝나 실제로 동작)',
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
  PRIMARY KEY (`checkpoint_id`),
  UNIQUE KEY `UQ_checkpoint_seq` (`project_id`, `seq`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='루트의 구간(1 depth). 구간 수 최대 8개(베이스캠프 제외, 팀 확정 11/25) — 앱에서 검사';

CREATE TABLE `checkpoint_tasks` (
  `task_id`             BIGINT       NOT NULL AUTO_INCREMENT COMMENT '구간 할 일 ID',
  `checkpoint_id`       BIGINT       NOT NULL COMMENT '구간',
  `role_id`             BIGINT       NOT NULL COMMENT '담당 역할 자리(사람보다 먼저 배정)',
  `assignee_member_id`  BIGINT       NULL     COMMENT '담당자(자리에 사람이 들어오면 넘겨받음)',
  `title`               VARCHAR(255) NOT NULL COMMENT '할 일',
  `reason`              VARCHAR(500) NULL     COMMENT 'AI 추천 이유',
  `origin`              VARCHAR(10)  NOT NULL COMMENT '출처 태그: plan(기획안 · 기본으로 담김) | ai(AI 추천 · 직접 골라야 담김) | manual(팀이 직접 추가)',
  `state`               VARCHAR(10)  NOT NULL COMMENT 'suggested(제안) | selected(담음) | done(끝남) | dismissed(안 고름). 처음 값: plan → selected, ai → suggested',
  `done_at`             DATETIME     NULL     COMMENT '끝낸 시각',
  `created_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  PRIMARY KEY (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='구간별 세부 할 일(2 depth, 3 depth 없음). 파트(역할)별. 덜 끝난 할 일도 원래 구간에 남음(팀 확정 11/25). 고른 기록이 다음 구간 추천의 입력';

-- ---------------------------------------------------------------------
-- C. 넘겨주기 카드(요청) · 주고받은 기록
-- ---------------------------------------------------------------------

CREATE TABLE `handoff_cards` (
  `card_id`            VARCHAR(64)  NOT NULL COMMENT '카드 ID(프론트가 만들어 보냄)',
  `project_id`         BIGINT       NOT NULL COMMENT '원정대',
  `group_id`           VARCHAR(64)  NULL     COMMENT '여러 역할에게 한 번에 보낸 요청이면 같은 값(받는 역할마다 카드 1장씩, 확인도 따로)',
  `checkpoint_id`      BIGINT       NULL     COMMENT '소속 구간(안 고르면 지금 구간)',
  `title`              VARCHAR(255) NOT NULL COMMENT '항목 이름(로그인 API …)',
  `from_role_id`       BIGINT       NOT NULL COMMENT '만들어 보내는 역할',
  `to_role_id`         BIGINT       NOT NULL COMMENT '받는 역할',
  `maker_user_id`      BIGINT       NULL     COMMENT '보내는 쪽 담당자(비면 역할 자리)',
  `requester_user_id`  BIGINT       NULL     COMMENT '받는 쪽(요청한) 사람',
  `origin`             VARCHAR(10)  NOT NULL COMMENT 'request(받는 쪽이 요청) | handoff(보내는 쪽이 바로 넘김)',
  `description`        TEXT         NULL     COMMENT '설명',
  `due_at`             DATETIME     NULL     COMMENT '희망 마감(날짜로 바꿀 수 있을 때)',
  `due_label`          VARCHAR(50)  NOT NULL COMMENT '화면 글자 그대로(11/21 (금) 18:00, 체크포인트 2)',
  `proposed_due_at`    DATETIME     NULL     COMMENT '보내는 쪽이 제안한 다른 날짜',
  `proposed_due_label` VARCHAR(50)  NULL     COMMENT '제안 날짜 화면 글자',
  `status`             VARCHAR(10)  NOT NULL DEFAULT 'requested' COMMENT 'requested | accepted(진행) | delivered(확인 대기) | confirmed(확인 완료)',
  `blocked_since`      DATE         NULL     COMMENT '막힌 날(NULL 이면 안 막힘)',
  `blocked_reason`     VARCHAR(255) NULL     COMMENT '막힌 이유',
  `tag`                VARCHAR(50)  NULL     COMMENT '작은 칩(PR #24)',
  `is_auto`            BOOLEAN      NOT NULL DEFAULT FALSE COMMENT 'GitHub 배포로 자동 전달된 카드',
  `github_pr_id`       BIGINT       NULL     COMMENT '연결된 PR (2차)',
  `review_path`        VARCHAR(255) NULL     COMMENT '결과물 검토 화면 주소(버전 비교)',
  `confirmed_at`       DATETIME     NULL     COMMENT '확인 완료 시각',
  `created_by`         BIGINT       NOT NULL COMMENT '카드를 만든 사람',
  `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  `updated_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
  PRIMARY KEY (`card_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='넘겨주기 카드(요청 → 수락 → 진행 → 전달 → 확인)';

CREATE TABLE `card_links` (
  `link_id`    BIGINT       NOT NULL AUTO_INCREMENT COMMENT '링크 ID',
  `card_id`    VARCHAR(64)  NOT NULL COMMENT '카드',
  `kind`       VARCHAR(10)  NOT NULL DEFAULT 'other' COMMENT 'figma | prototype | github | api_doc | other',
  `title`      VARCHAR(255) NOT NULL COMMENT '보이는 이름(Figma 로그인 화면 v2)',
  `url`        VARCHAR(700) NULL     COMMENT '주소',
  `sort_order` INT          NOT NULL DEFAULT 0 COMMENT '순서',
  PRIMARY KEY (`link_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='카드 참고 링크';

CREATE TABLE `card_events` (
  `event_id`       VARCHAR(64)  NOT NULL COMMENT '기록 ID(프론트가 만들어 보냄)',
  `card_id`        VARCHAR(64)  NOT NULL COMMENT '카드',
  `kind`           VARCHAR(10)  NOT NULL COMMENT 'request | accept | propose | question | comment | deliver | fix | redeliver | confirm | block | unblock',
  `author_user_id` BIGINT       NOT NULL COMMENT '누가',
  `author_role_id` BIGINT       NULL     COMMENT '어느 역할로',
  `text`           TEXT         NOT NULL COMMENT '무엇을(질문 · 수정 요청 내용 …)',
  `result_title`   VARCHAR(255) NULL     COMMENT '전달일 때 결과물 이름(최종 결과물)',
  `result_url`     VARCHAR(700) NULL     COMMENT '전달일 때 결과물 주소',
  `created_at`     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '언제',
  PRIMARY KEY (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='주고받은 기록(알림도 여기서 만들어짐)';

-- ---------------------------------------------------------------------
-- D. 방(역할 방 · 전체 방) · 대화
-- ---------------------------------------------------------------------

CREATE TABLE `rooms` (
  `room_id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '방 ID',
  `project_id`         BIGINT       NOT NULL COMMENT '원정대',
  `role_id`            BIGINT       NULL     COMMENT '역할 방이면 역할, 전체 원정대 방이면 NULL',
  `name`               VARCHAR(50)  NOT NULL COMMENT '방 이름(디자인 방 · 전체 원정대)',
  `ai_summary`         VARCHAR(500) NULL     COMMENT 'AI 요약 한 줄',
  `summary_updated_at` DATETIME     NULL     COMMENT '요약 갱신 시각',
  `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
  PRIMARY KEY (`room_id`),
  UNIQUE KEY `UQ_room_role` (`project_id`, `role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='방(역할마다 하나 + 전체 방 하나)';

CREATE TABLE `room_messages` (
  `message_id`     VARCHAR(64) NOT NULL COMMENT '메시지 ID(프론트가 만들어 보냄)',
  `room_id`        BIGINT      NOT NULL COMMENT '보낸 방',
  `checkpoint_id`  BIGINT      NULL     COMMENT '소속 구간(시퀀스). 기본은 보낸 때의 지금 구간 → 구간별 대화 모아 보기',
  `author_user_id` BIGINT      NOT NULL COMMENT '보낸 사람',
  `author_role_id` BIGINT      NULL     COMMENT '보낸 사람 역할(아바타 색)',
  `body`           TEXT        NOT NULL COMMENT '내용',
  `is_notice`      BOOLEAN     NOT NULL DEFAULT FALSE COMMENT '전체 방 공지(세 방 모두에 보임)',
  `created_at`     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '보낸 시각',
  PRIMARY KEY (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='방 대화';

CREATE TABLE `message_attachments` (
  `attachment_id` BIGINT       NOT NULL AUTO_INCREMENT COMMENT '첨부 ID',
  `message_id`    VARCHAR(64)  NOT NULL COMMENT '메시지',
  `type`          VARCHAR(10)  NOT NULL COMMENT 'link | figma | pr | handoff',
  `source`        VARCHAR(10)  NULL     COMMENT 'FIGMA | GITHUB',
  `title`         VARCHAR(255) NOT NULL COMMENT '제목(로그인 화면 v2, #24 메인 화면 레이아웃)',
  `url`           VARCHAR(700) NULL     COMMENT '바깥 주소',
  `version_label` VARCHAR(50)  NULL     COMMENT 'Figma 버전(v2 · 1시간 전 수정)',
  `note`          VARCHAR(255) NULL     COMMENT '바뀐 곳 설명(버튼 높이 48로 수정)',
  `path`          VARCHAR(255) NULL     COMMENT 'Figma 위치(캠퍼스 앱 › 로그인 › …)',
  `github_pr_id`  BIGINT       NULL     COMMENT 'PR 카드면 PR (2차)',
  `card_id`       VARCHAR(64)  NULL     COMMENT '넘겨주기 배지면 그 카드',
  `sort_order`    INT          NOT NULL DEFAULT 0 COMMENT '순서',
  PRIMARY KEY (`attachment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='메시지 첨부(Figma 미리보기 · PR 카드 · 링크 칩 · 넘겨주기 배지)';

CREATE TABLE `room_reads` (
  `room_id`      BIGINT   NOT NULL COMMENT '방',
  `user_id`      BIGINT   NOT NULL COMMENT '사용자',
  `last_read_at` DATETIME NOT NULL COMMENT '마지막으로 읽은 시각(새 메시지 수 계산)',
  PRIMARY KEY (`room_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='방별 읽음 위치';

-- ---------------------------------------------------------------------
-- E. 알림
-- ---------------------------------------------------------------------

CREATE TABLE `notifications` (
  `notification_id` BIGINT      NOT NULL AUTO_INCREMENT COMMENT '알림 ID',
  `user_id`         BIGINT      NOT NULL COMMENT '받는 사람',
  `card_id`         VARCHAR(64) NOT NULL COMMENT '카드',
  `event_id`        VARCHAR(64) NOT NULL COMMENT '알림을 만든 기록(프론트 id = 카드id:기록id)',
  `is_read`         BOOLEAN     NOT NULL DEFAULT FALSE COMMENT '읽음 여부',
  `read_at`         DATETIME    NULL     COMMENT '읽은 시각',
  `created_at`      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생긴 시각',
  PRIMARY KEY (`notification_id`),
  UNIQUE KEY `UQ_notification_event` (`user_id`, `event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='알림(카드 기록 → 받는 사람별 한 줄)';

-- ---------------------------------------------------------------------
-- F. (2차) GitHub 연결 · 버전 비교 — Figma 화면은 있지만 위치·범위 확정 전
-- ---------------------------------------------------------------------

CREATE TABLE `github_repositories` (
  `repo_id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '연결한 저장소 ID',
  `project_id`      BIGINT       NOT NULL COMMENT '원정대',
  `owner`           VARCHAR(100) NOT NULL COMMENT 'GitHub 소유자',
  `name`            VARCHAR(100) NOT NULL COMMENT '저장소 이름(campus-app)',
  `installation_id` VARCHAR(50)  NULL     COMMENT 'GitHub App 설치 ID',
  `connected_by`    BIGINT       NOT NULL COMMENT '연결한 사람',
  `connected_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '연결일시',
  PRIMARY KEY (`repo_id`),
  UNIQUE KEY `UQ_project_repo` (`project_id`, `owner`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='GitHub 연결';

CREATE TABLE `github_pull_requests` (
  `pr_id`        BIGINT       NOT NULL AUTO_INCREMENT COMMENT 'PR ID',
  `repo_id`      BIGINT       NOT NULL COMMENT '저장소',
  `number`       INT          NOT NULL COMMENT 'PR 번호(#24)',
  `title`        VARCHAR(255) NOT NULL COMMENT 'PR 제목',
  `head_branch`  VARCHAR(255) NOT NULL COMMENT '작업 브랜치',
  `base_branch`  VARCHAR(255) NOT NULL COMMENT '합칠 브랜치',
  `author_login` VARCHAR(100) NULL     COMMENT '작성자 GitHub 아이디',
  `stage`        VARCHAR(10)  NOT NULL DEFAULT 'work' COMMENT 'work(작업) | review(리뷰) | merged(병합) | deployed(배포)',
  `url`          VARCHAR(500) NOT NULL COMMENT 'PR 주소',
  `merged_at`    DATETIME     NULL     COMMENT '병합 시각',
  `deployed_at`  DATETIME     NULL     COMMENT '배포 시각(연결된 카드 자동 전달)',
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '갱신일시',
  PRIMARY KEY (`pr_id`),
  UNIQUE KEY `UQ_repo_pr_number` (`repo_id`, `number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='PR 진행 단계(작업 → 리뷰 → 병합 → 배포)';

CREATE TABLE `app_versions` (
  `app_version_id` BIGINT       NOT NULL AUTO_INCREMENT COMMENT '배포 버전 ID',
  `project_id`     BIGINT       NOT NULL COMMENT '원정대',
  `environment`    VARCHAR(10)  NOT NULL COMMENT 'prod(지금 서비스 중) | dev(개발 서버)',
  `version_label`  VARCHAR(50)  NOT NULL COMMENT 'v1.3.0',
  `branch`         VARCHAR(100) NULL     COMMENT 'main | dev',
  `site_url`       VARCHAR(700) NOT NULL COMMENT '화면을 불러올 주소',
  `source_pr_id`   BIGINT       NULL     COMMENT '이 배포를 만든 PR',
  `deployed_at`    DATETIME     NOT NULL COMMENT '배포 시각',
  PRIMARY KEY (`app_version_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='버전 비교용 배포 기록';

CREATE TABLE `compare_comments` (
  `comment_id`        BIGINT       NOT NULL AUTO_INCREMENT COMMENT '코멘트 ID',
  `app_version_id`    BIGINT       NOT NULL COMMENT '어느 버전 화면 위인지',
  `screen_name`       VARCHAR(100) NOT NULL COMMENT '화면(메인 피드)',
  `pin_x`             INT          NULL     COMMENT '핀 x',
  `pin_y`             INT          NULL     COMMENT '핀 y',
  `author_user_id`    BIGINT       NOT NULL COMMENT '작성자',
  `author_role_id`    BIGINT       NULL     COMMENT '디자인 코멘트 · 프론트 코멘트 구분',
  `kind`              VARCHAR(10)  NOT NULL DEFAULT 'comment' COMMENT 'comment | memo',
  `body`              TEXT         NOT NULL COMMENT '내용',
  `parent_comment_id` BIGINT       NULL     COMMENT '답글이면 원 코멘트',
  `resolved_by`       BIGINT       NULL     COMMENT '해결로 표시한 사람',
  `resolved_at`       DATETIME     NULL     COMMENT '해결 시각',
  `card_id`           VARCHAR(64)  NULL     COMMENT '"넘겨주기로 만들기"로 생긴 카드',
  `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '작성일시',
  PRIMARY KEY (`comment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='버전 비교 화면 위 코멘트';

-- ---------------------------------------------------------------------
-- G. (2차) 완주 · 회고
-- ---------------------------------------------------------------------

CREATE TABLE `retrospectives` (
  `retrospective_id` BIGINT   NOT NULL AUTO_INCREMENT COMMENT '회고 ID',
  `project_id`       BIGINT   NOT NULL COMMENT '원정대',
  `author_user_id`   BIGINT   NOT NULL COMMENT '작성자',
  `body`             TEXT     NOT NULL COMMENT '회고 내용',
  `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '작성일시',
  PRIMARY KEY (`retrospective_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='정상 도착 후 회고';

-- =====================================================================
-- 외래키
-- =====================================================================

ALTER TABLE `user_identities`      ADD CONSTRAINT `FK_users_TO_user_identities`        FOREIGN KEY (`user_id`)            REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `workspaces`           ADD CONSTRAINT `FK_users_TO_workspaces`             FOREIGN KEY (`created_by`)         REFERENCES `users` (`user_id`);
ALTER TABLE `workspace_members`    ADD CONSTRAINT `FK_workspaces_TO_workspace_members` FOREIGN KEY (`workspace_id`)       REFERENCES `workspaces` (`workspace_id`) ON DELETE CASCADE;
ALTER TABLE `workspace_members`    ADD CONSTRAINT `FK_users_TO_workspace_members`      FOREIGN KEY (`user_id`)            REFERENCES `users` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `projects`             ADD CONSTRAINT `FK_workspaces_TO_projects`          FOREIGN KEY (`workspace_id`)       REFERENCES `workspaces` (`workspace_id`) ON DELETE CASCADE;
ALTER TABLE `projects`             ADD CONSTRAINT `FK_users_TO_projects`               FOREIGN KEY (`created_by`)         REFERENCES `users` (`user_id`);
ALTER TABLE `plan_documents`       ADD CONSTRAINT `FK_projects_TO_plan_documents`      FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `plan_documents`       ADD CONSTRAINT `FK_users_TO_plan_documents`         FOREIGN KEY (`uploaded_by`)        REFERENCES `users` (`user_id`);
ALTER TABLE `project_roles`        ADD CONSTRAINT `FK_projects_TO_project_roles`       FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `project_members`      ADD CONSTRAINT `FK_projects_TO_project_members`     FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `project_members`      ADD CONSTRAINT `FK_users_TO_project_members`        FOREIGN KEY (`user_id`)            REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `project_member_roles` ADD CONSTRAINT `FK_members_TO_member_roles`         FOREIGN KEY (`member_id`)          REFERENCES `project_members` (`member_id`) ON DELETE CASCADE;
ALTER TABLE `project_member_roles` ADD CONSTRAINT `FK_roles_TO_member_roles`           FOREIGN KEY (`role_id`)            REFERENCES `project_roles` (`role_id`) ON DELETE CASCADE;
ALTER TABLE `project_invitations`  ADD CONSTRAINT `FK_projects_TO_invitations`         FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `project_invitations`  ADD CONSTRAINT `FK_users_TO_invitations_inviter`    FOREIGN KEY (`invited_by`)         REFERENCES `users` (`user_id`);
ALTER TABLE `project_invitations`  ADD CONSTRAINT `FK_users_TO_invitations_accepter`   FOREIGN KEY (`accepted_by`)        REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `invitation_roles`     ADD CONSTRAINT `FK_invitations_TO_invitation_roles` FOREIGN KEY (`invitation_id`)      REFERENCES `project_invitations` (`invitation_id`) ON DELETE CASCADE;
ALTER TABLE `invitation_roles`     ADD CONSTRAINT `FK_roles_TO_invitation_roles`       FOREIGN KEY (`role_id`)            REFERENCES `project_roles` (`role_id`) ON DELETE CASCADE;
ALTER TABLE `checkpoints`          ADD CONSTRAINT `FK_projects_TO_checkpoints`         FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `checkpoint_tasks`     ADD CONSTRAINT `FK_checkpoints_TO_tasks`            FOREIGN KEY (`checkpoint_id`)      REFERENCES `checkpoints` (`checkpoint_id`) ON DELETE CASCADE;
ALTER TABLE `checkpoint_tasks`     ADD CONSTRAINT `FK_roles_TO_tasks`                  FOREIGN KEY (`role_id`)            REFERENCES `project_roles` (`role_id`);
ALTER TABLE `checkpoint_tasks`     ADD CONSTRAINT `FK_members_TO_tasks`                FOREIGN KEY (`assignee_member_id`) REFERENCES `project_members` (`member_id`) ON DELETE SET NULL;

ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_projects_TO_cards`               FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_checkpoints_TO_cards`            FOREIGN KEY (`checkpoint_id`)      REFERENCES `checkpoints` (`checkpoint_id`) ON DELETE SET NULL;
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_roles_TO_cards_from`             FOREIGN KEY (`from_role_id`)       REFERENCES `project_roles` (`role_id`);
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_roles_TO_cards_to`               FOREIGN KEY (`to_role_id`)         REFERENCES `project_roles` (`role_id`);
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_users_TO_cards_maker`            FOREIGN KEY (`maker_user_id`)      REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_users_TO_cards_requester`        FOREIGN KEY (`requester_user_id`)  REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_users_TO_cards_creator`          FOREIGN KEY (`created_by`)         REFERENCES `users` (`user_id`);
ALTER TABLE `handoff_cards`        ADD CONSTRAINT `FK_prs_TO_cards`                    FOREIGN KEY (`github_pr_id`)       REFERENCES `github_pull_requests` (`pr_id`) ON DELETE SET NULL;
ALTER TABLE `card_links`           ADD CONSTRAINT `FK_cards_TO_card_links`             FOREIGN KEY (`card_id`)            REFERENCES `handoff_cards` (`card_id`) ON DELETE CASCADE;
ALTER TABLE `card_events`          ADD CONSTRAINT `FK_cards_TO_card_events`            FOREIGN KEY (`card_id`)            REFERENCES `handoff_cards` (`card_id`) ON DELETE CASCADE;
ALTER TABLE `card_events`          ADD CONSTRAINT `FK_users_TO_card_events`            FOREIGN KEY (`author_user_id`)     REFERENCES `users` (`user_id`);
ALTER TABLE `card_events`          ADD CONSTRAINT `FK_roles_TO_card_events`            FOREIGN KEY (`author_role_id`)     REFERENCES `project_roles` (`role_id`) ON DELETE SET NULL;

ALTER TABLE `rooms`                ADD CONSTRAINT `FK_projects_TO_rooms`               FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `rooms`                ADD CONSTRAINT `FK_roles_TO_rooms`                  FOREIGN KEY (`role_id`)            REFERENCES `project_roles` (`role_id`) ON DELETE CASCADE;
ALTER TABLE `room_messages`        ADD CONSTRAINT `FK_rooms_TO_messages`               FOREIGN KEY (`room_id`)            REFERENCES `rooms` (`room_id`) ON DELETE CASCADE;
ALTER TABLE `room_messages`        ADD CONSTRAINT `FK_checkpoints_TO_messages`         FOREIGN KEY (`checkpoint_id`)      REFERENCES `checkpoints` (`checkpoint_id`) ON DELETE SET NULL;
ALTER TABLE `room_messages`        ADD CONSTRAINT `FK_users_TO_messages`               FOREIGN KEY (`author_user_id`)     REFERENCES `users` (`user_id`);
ALTER TABLE `room_messages`        ADD CONSTRAINT `FK_roles_TO_messages`               FOREIGN KEY (`author_role_id`)     REFERENCES `project_roles` (`role_id`) ON DELETE SET NULL;
ALTER TABLE `message_attachments`  ADD CONSTRAINT `FK_messages_TO_attachments`         FOREIGN KEY (`message_id`)         REFERENCES `room_messages` (`message_id`) ON DELETE CASCADE;
ALTER TABLE `message_attachments`  ADD CONSTRAINT `FK_prs_TO_attachments`              FOREIGN KEY (`github_pr_id`)       REFERENCES `github_pull_requests` (`pr_id`) ON DELETE SET NULL;
ALTER TABLE `message_attachments`  ADD CONSTRAINT `FK_cards_TO_attachments`            FOREIGN KEY (`card_id`)            REFERENCES `handoff_cards` (`card_id`) ON DELETE SET NULL;
ALTER TABLE `room_reads`           ADD CONSTRAINT `FK_rooms_TO_room_reads`             FOREIGN KEY (`room_id`)            REFERENCES `rooms` (`room_id`) ON DELETE CASCADE;
ALTER TABLE `room_reads`           ADD CONSTRAINT `FK_users_TO_room_reads`             FOREIGN KEY (`user_id`)            REFERENCES `users` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `notifications`        ADD CONSTRAINT `FK_users_TO_notifications`          FOREIGN KEY (`user_id`)            REFERENCES `users` (`user_id`) ON DELETE CASCADE;
ALTER TABLE `notifications`        ADD CONSTRAINT `FK_cards_TO_notifications`          FOREIGN KEY (`card_id`)            REFERENCES `handoff_cards` (`card_id`) ON DELETE CASCADE;
ALTER TABLE `notifications`        ADD CONSTRAINT `FK_events_TO_notifications`         FOREIGN KEY (`event_id`)           REFERENCES `card_events` (`event_id`) ON DELETE CASCADE;

ALTER TABLE `github_repositories`  ADD CONSTRAINT `FK_projects_TO_repositories`        FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `github_repositories`  ADD CONSTRAINT `FK_users_TO_repositories`           FOREIGN KEY (`connected_by`)       REFERENCES `users` (`user_id`);
ALTER TABLE `github_pull_requests` ADD CONSTRAINT `FK_repositories_TO_prs`             FOREIGN KEY (`repo_id`)            REFERENCES `github_repositories` (`repo_id`) ON DELETE CASCADE;
ALTER TABLE `app_versions`         ADD CONSTRAINT `FK_projects_TO_app_versions`        FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `app_versions`         ADD CONSTRAINT `FK_prs_TO_app_versions`             FOREIGN KEY (`source_pr_id`)       REFERENCES `github_pull_requests` (`pr_id`) ON DELETE SET NULL;
ALTER TABLE `compare_comments`     ADD CONSTRAINT `FK_versions_TO_compare_comments`    FOREIGN KEY (`app_version_id`)     REFERENCES `app_versions` (`app_version_id`) ON DELETE CASCADE;
ALTER TABLE `compare_comments`     ADD CONSTRAINT `FK_users_TO_compare_comments`       FOREIGN KEY (`author_user_id`)     REFERENCES `users` (`user_id`);
ALTER TABLE `compare_comments`     ADD CONSTRAINT `FK_roles_TO_compare_comments`       FOREIGN KEY (`author_role_id`)     REFERENCES `project_roles` (`role_id`) ON DELETE SET NULL;
ALTER TABLE `compare_comments`     ADD CONSTRAINT `FK_comments_TO_compare_comments`    FOREIGN KEY (`parent_comment_id`)  REFERENCES `compare_comments` (`comment_id`) ON DELETE CASCADE;
ALTER TABLE `compare_comments`     ADD CONSTRAINT `FK_users_TO_compare_resolver`       FOREIGN KEY (`resolved_by`)        REFERENCES `users` (`user_id`) ON DELETE SET NULL;
ALTER TABLE `compare_comments`     ADD CONSTRAINT `FK_cards_TO_compare_comments`       FOREIGN KEY (`card_id`)            REFERENCES `handoff_cards` (`card_id`) ON DELETE SET NULL;
ALTER TABLE `retrospectives`       ADD CONSTRAINT `FK_projects_TO_retrospectives`      FOREIGN KEY (`project_id`)         REFERENCES `projects` (`project_id`) ON DELETE CASCADE;
ALTER TABLE `retrospectives`       ADD CONSTRAINT `FK_users_TO_retrospectives`         FOREIGN KEY (`author_user_id`)     REFERENCES `users` (`user_id`);
