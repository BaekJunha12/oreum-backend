# Contributing

## 커밋 메시지 규칙

형식은 **`[태그] 한 줄 설명`** 하나뿐이에요.

```
[feat] Add project invitation API
[fix] Fix #7 login redirect loop
[design] Move route button to the board header
[docs] 원정대 초대 API 명세 추가
```

| 태그 | 쓰는 경우 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정. 이슈가 있으면 번호를 적어요 (`Fix #7 ...`) |
| `design` | UI·화면 변경 (CSS, 레이아웃, 문구·버튼 위치) |
| `style` | 코드 포맷만 변경 (들여쓰기, 따옴표 등, 동작 변화 없음) |
| `refactor` | 동작은 그대로 두고 구조 개선 |
| `docs` | 문서 (README, 명세서, 주석) |
| `test` | 테스트 추가·수정 |
| `chore` | 설정, 의존성, 빌드, 기타 잡무 |

규칙:

- 태그는 위 8개 중 하나, 소문자, 대괄호 뒤 공백 한 칸
- 제목은 한 줄, 72자 이내 (한글도 1자), 끝에 마침표 없음
- 본문은 쓰지 않아요. 예외로 같이 작업한 사람을 남기는 `Co-authored-by: 이름 <이메일>` 줄만 허용해요
- 한 커밋에는 한 가지 일만. 태그가 두 개 필요하면 커밋을 나눠요
- 한국어·영어 모두 가능하지만, 한 PR 안에서는 한 언어로 맞춰요

## 처음 클론하고 한 번만

```bash
git config core.hooksPath .githooks    # 규칙에 안 맞는 커밋을 로컬에서 바로 막음
git config commit.template .gitmessage  # git commit 시 편집기에 태그 목록이 보임
```

훅이 막으면 이렇게 나와요.

```
✖ 커밋 메시지 규칙 위반: 제목이 '[태그] 설명' 형식이 아니에요
  입력: add login api
  형식: [태그] 한 줄 설명   예) [feat] Add project invitation API
```

방금 한 커밋 메시지를 고치려면 `git commit --amend`를 쓰면 돼요 (푸시 전에만).

## Pull Request

- PR 제목도 같은 형식으로 써요. 스쿼시 머지하면 PR 제목이 그대로 커밋 메시지가 돼요
- PR을 열면 GitHub Actions(`commit-convention`)가 PR 제목과 모든 커밋 메시지를 검사해요. 머지 커밋은 검사하지 않아요
- 브랜치 이름도 태그를 따라가면 찾기 쉬워요: `feat/project-invite`, `fix/7-login-redirect`

## 관련 파일

| 파일 | 역할 |
|---|---|
| `scripts/check-commit-msg.sh` | 규칙 검사기 (훅과 CI가 같이 씀). 태그를 추가하려면 여기 `TYPES`와 이 문서를 같이 고쳐요 |
| `.githooks/commit-msg` | 로컬 커밋 훅 |
| `.gitmessage` | 커밋 템플릿 |
| `.github/workflows/commit-convention.yml` | PR 검사 |
