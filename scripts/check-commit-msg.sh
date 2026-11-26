#!/usr/bin/env bash
# 커밋 메시지 규칙 검사기 (로컬 commit-msg 훅과 GitHub Actions가 같이 씀)
# 사용법: scripts/check-commit-msg.sh <메시지 파일>
set -euo pipefail

TYPES="feat|fix|design|style|refactor|docs|test|chore"   # 허용 태그 목록 (CONTRIBUTING.md와 같이 관리)
MAX_LEN=72                                               # 제목 최대 글자 수 (한글도 1글자로 셈)
file="$1"

# git 템플릿 주석(#) 제거 (끝쪽 빈 줄은 $(...)가 자동으로 지움)
msg="$(grep -v '^#' "$file" || true)"
subject="$(printf '%s\n' "$msg" | head -n 1)"            # 첫 줄 = 제목
rest="$(printf '%s\n' "$msg" | tail -n +2)"              # 나머지 줄

fail() {
  echo "✖ 커밋 메시지 규칙 위반: $1" >&2
  echo "  입력: ${subject}" >&2
  echo "  형식: [태그] 한 줄 설명   예) [feat] Add project invitation API" >&2
  echo "  태그: ${TYPES//|/, }" >&2
  exit 1
}

# 1) 제목 형식: [태그] + 공백 1칸 + 내용
printf '%s' "$subject" | grep -Eq "^\[(${TYPES})\] [^ ].*" || fail "제목이 '[태그] 설명' 형식이 아니에요"
# 2) 마침표로 끝나지 않기
printf '%s' "$subject" | grep -Eq '\.$' && fail "제목 끝에 마침표를 붙이지 않아요"
# 3) 길이 제한 (perl로 UTF-8 글자 수 계산 → 한글도 정확히 셈)
len="$(printf '%s' "$subject" | perl -CI -ne 'print length')"
[ "$len" -le "$MAX_LEN" ] || fail "제목이 ${len}자예요 (최대 ${MAX_LEN}자)"
# 4) 본문 금지: 빈 줄과 Co-authored-by 트레일러만 허용
extra="$(printf '%s\n' "$rest" | grep -Eiv '^[[:space:]]*$|^Co-authored-by: .+ <.+>$' || true)"
[ -z "$extra" ] || fail "제목 한 줄만 써요 (본문 불가, Co-authored-by 줄만 허용)"

exit 0
