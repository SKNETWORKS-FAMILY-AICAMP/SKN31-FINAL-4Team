#!/usr/bin/env bash
# Use the monorepo frontend and its lockfile-managed jsdom installation.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
web="${FEEDIT_WEB:-$here/../../frontend}"
web="$(cd "$web" && pwd)"
[ -d "$web/home" ] || { echo "frontend를 찾을 수 없습니다: $web"; exit 2; }
[ -f "$web/node_modules/jsdom/package.json" ] || {
  echo "먼저 frontend에서 npm ci를 실행하세요."; exit 2;
}
stage="$(mktemp -d "${TMPDIR:-/tmp}/feedit-chat-tests.XXXXXX")"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/app" "$stage/css"
cp "$here"/*.test.mjs "$here"/browser_env.mjs "$here"/popup.html "$stage"/
cp "$web/index.html" "$stage/app_index.html"
cp "$web/main.js" "$stage/app/main.js"   # 앱 진입점 — 모듈을 실제 순서대로 불러온다
cp -r "$here/sse" "$stage/"
cp "$here/fixtures.json" "$stage/_chat_fixtures.json"
for dir in "$web"/*/static/js; do
  [ -d "$dir" ] || continue
  feature="$(basename "$(dirname "$(dirname "$dir")")")"
  mkdir -p "$stage/app/$feature/static"
  cp -R "$dir" "$stage/app/$feature/static/js"
done
# Keep chat_api's relative imports rooted in the original feature layout.
printf '%s\n' 'export * from "./app/home/static/js/chat_api.js";' > "$stage/chat_api.js"
printf '%s\n' '{"type":"module"}' > "$stage/package.json"
find "$web" -name '*.css' -not -path '*/node_modules/*' -not -path '*/dist/*' -exec cp {} "$stage/css/" \;
ln -s "$web/node_modules" "$stage/node_modules"
cd "$stage"
fail=0
for test_file in *.test.mjs; do
  printf '\n── %s\n' "$test_file"
  node "$test_file" || fail=1
done
[ "$fail" = 0 ] && echo "전부 통과" || echo "실패 있음"
exit "$fail"
