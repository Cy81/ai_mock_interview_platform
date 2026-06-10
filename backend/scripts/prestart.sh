#!/bin/sh
set -eu

alembic upgrade head

if [ "${ENVIRONMENT:-development}" = "production" ]; then
  echo "production environment detected; skipping development seed data"
else
  python scripts/seed_data.py
fi
