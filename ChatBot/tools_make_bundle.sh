#!/usr/bin/env bash
# ⚠ 2026-09-23 — 운영(RDS 모드)에는 더 이상 필요 없다.
#   어휘 추출기·Lexicon 은 ChatBot/vendor/ 에 들어 있어 이미지에 함께 실린다.
#   이 스크립트는 SQLite 지표 DB 를 서버로 옮겨야 하는 옛 방식에서만 쓴다.
#
# 챗봇이 돌아가는 데 **꼭 필요한 것만** 묶는다.
#
# ── 왜 이게 필요한가 ──────────────────────────────────────
# 크롤러 저장소는 1.6GB 다. 그런데 챗봇이 실제로 읽는 건 다섯 개뿐이고
# 합쳐서 42MB 다. 서버에 크롤러를 통째로 올릴 이유가 없다.
#
#   crawler/data/feedit.db              지표 (VACUUM INTO 로 새로 만든 단일 파일)
#   crawler/config/lexicon.yaml         어휘 사전
#   crawler/feedit_crawler/lexicon.py   lexicon_gate 가 import
#   crawler/feedit_crawler/__init__.py  위 import 를 위한 패키지 표시
#   tools/question_extract.py           어휘 추출기
#
# 둘 다 표준 라이브러리와 PyYAML 만 쓴다 — 크롤러의 다른 코드를 안 끌고 온다.
# (2026-09-08 확인: 이 다섯 개만으로 엔진이 부팅되고 답까지 나온다)
#
# ── 쓰는 법 ──────────────────────────────────────────────
#   ./tools_make_bundle.sh                     .env 의 경로를 쓴다
#   ./tools_make_bundle.sh /경로/feedit-crawler /경로/tools
#
# 결과: feedit-chat-bundle.tar.gz
#   scp feedit-chat-bundle.tar.gz  ec2-user@서버:/tmp/
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"

# 경로: 인자 > .env > 포기
CRAWLER="${1:-}"
TOOLS="${2:-}"
if [ -z "$CRAWLER" ] && [ -f "$REPO/.env" ]; then
  CRAWLER=$(grep -E '^FEEDIT_CRAWLER_DIR=' "$REPO/.env" | tail -1 | cut -d= -f2-)
  TOOLS=$(grep -E '^FEEDIT_EXTRACTOR_DIR=' "$REPO/.env" | tail -1 | cut -d= -f2- || true)
fi
[ -n "${TOOLS:-}" ] || TOOLS="$HERE/vendor"

if [ -z "$CRAWLER" ] || [ ! -d "$CRAWLER" ]; then
  echo "크롤러 저장소를 못 찾았습니다: '${CRAWLER:-(비어 있음)}'" >&2
  echo "  .env 에 FEEDIT_CRAWLER_DIR 을 넣거나, 인자로 주세요." >&2
  exit 1
fi

OUT="$HERE/feedit-chat-bundle.tar.gz"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/bundle/crawler/data" \
         "$STAGE/bundle/crawler/config" \
         "$STAGE/bundle/crawler/feedit_crawler" \
         "$STAGE/bundle/tools"

need() {   # 없으면 그 자리에서 멈춘다 — 반쪽 묶음을 서버에 올리면 거기서 헤맨다
  [ -f "$1" ] || { echo "없습니다: $1" >&2; exit 1; }
  cp "$1" "$2"
}
# ★ DB 는 그냥 복사하지 않는다. VACUUM INTO 로 새로 만든다.
#
#   크롤러 DB 는 **WAL 모드**다. 그러면 feedit.db 하나만 떼어 가는 것으로는
#   부족하다 — 최근 커밋이 아직 feedit.db-wal 에 남아 있고, SQLite 는
#   WAL DB 를 읽기 전용으로 열 때도 -shm 을 만들려 든다.
#   그래서 읽기 전용 마운트(:ro)에 올리면 이렇게 죽는다:
#
#       sqlite3.OperationalError: unable to open database file
#
#   (2026-09-08 서버에서 실제로 이 오류를 봤다. 로컬에서는 폴더가
#    쓰기 가능해서 안 났고, 그래서 여기까지 와서야 드러났다.)
#
#   VACUUM INTO 는 WAL 내용을 합친 **단일 파일**을 만들고 저널 모드도
#   delete 로 떨어진다. -wal · -shm 이 필요 없어진다.
[ -f "$CRAWLER/data/feedit.db" ] || { echo "없습니다: $CRAWLER/data/feedit.db" >&2; exit 1; }
python3 - "$CRAWLER/data/feedit.db" "$STAGE/bundle/crawler/data/feedit.db" <<'PY'
import sqlite3, sys
src, out = sys.argv[1], sys.argv[2]
c = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
c.execute("VACUUM INTO ?", (out,))
c.close()
d = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
mode = d.execute("PRAGMA journal_mode").fetchone()[0]
rows = d.execute("SELECT count(*) FROM metric_term_daily").fetchone()[0]
day  = d.execute("SELECT max(observed_on) FROM metric_term_daily").fetchone()[0]
d.close()
assert mode != "wal", f"저널 모드가 아직 {mode} 입니다"
print(f"  DB: {rows:,}행 · 최신 {day} · journal={mode}")
PY
need "$CRAWLER/config/lexicon.yaml"        "$STAGE/bundle/crawler/config/"
need "$CRAWLER/feedit_crawler/lexicon.py"  "$STAGE/bundle/crawler/feedit_crawler/"
need "$CRAWLER/feedit_crawler/__init__.py" "$STAGE/bundle/crawler/feedit_crawler/"
need "$TOOLS/question_extract.py"          "$STAGE/bundle/tools/"

# COPYFILE_DISABLE — 맥 tar 가 확장속성을 ._파일로 같이 넣는 것을 막는다.
#   그게 있으면 리눅스에서 풀 때 경고가 쏟아지고 ._feedit.db 같은 찌꺼기가 남는다.
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$OUT" -C "$STAGE" bundle 2>/dev/null \
  || COPYFILE_DISABLE=1 tar -czf "$OUT" -C "$STAGE" bundle

echo "만들었습니다: $OUT  ($(du -h "$OUT" | cut -f1))"
echo
echo "서버에 올리기:"
echo "  scp $OUT  <사용자>@<서버>:/tmp/"
echo
echo "서버에서 풀기:"
echo "  sudo mkdir -p /opt/feedit-chat-data"
echo "  sudo tar -xzf /tmp/feedit-chat-bundle.tar.gz -C /opt/feedit-chat-data --strip-components=1"
echo
echo "서버 .env 에 두 줄:"
echo "  FEEDIT_CRAWLER_DIR=/opt/feedit-chat-data/crawler"
echo "  FEEDIT_EXTRACTOR_DIR=/opt/feedit-chat-data/tools"
