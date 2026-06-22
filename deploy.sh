#!/usr/bin/env bash
# 좌우지간 재배포: 피드/정적페이지 재생성 → gh-pages 브랜치로 푸시 (GitHub Pages 갱신)
# 사용: ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo "① 피드 재생성 (build_html.py)…"
python3 build_html.py >/dev/null
cp assembly_votes.html out/index.html

echo "② 정적페이지·사이트맵 재생성 (build_static.py)…"
python3 build_static.py >/dev/null
touch out/.nojekyll

echo "③ gh-pages 배포…"
WT="/tmp/zwjg-ghpages"
rm -rf "$WT"; git worktree prune
git worktree add -B gh-pages "$WT" >/dev/null
(
  cd "$WT"
  git rm -rqf . >/dev/null 2>&1 || true
  cp -R "$ROOT/out/." .
  git add -A
  git commit -q -m "deploy: $(date '+%Y-%m-%d %H:%M')" || { echo "변경 없음"; exit 0; }
  git push -fq origin gh-pages
)
git worktree remove --force "$WT"

OVW=$(python3 -c "import json;print(len(json.load(open('overviews_gemini.json'))))" 2>/dev/null || echo "?")
echo "✅ 배포 완료 (AI 개요 ${OVW}건) → https://brbrlim.github.io/assembly-vote/"
echo "   (Pages 반영까지 1~2분)"
