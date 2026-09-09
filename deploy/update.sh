#!/usr/bin/env bash
# 서버에서 코드를 최신으로 올리고 봇을 다시 띄운다.
#   ~/maple_schedule_reminder/deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."
echo "== 저장소 갱신 =="
git pull --ff-only

echo "== 의존성 =="
.venv/bin/pip install -q -e .

echo "== DB 마이그레이션 =="
.venv/bin/python -m alembic upgrade head

echo "== 재시작 =="
sudo systemctl restart maple-bot
sleep 3
sudo systemctl --no-pager --lines=15 status maple-bot
