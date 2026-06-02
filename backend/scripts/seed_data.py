"""开发期种子脚本：仅用于本地 / dev 环境，不要在生产运行。"""
from __future__ import annotations

import structlog

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, init_db
from app.services.bootstrap import bootstrap_data


def main() -> None:
    configure_logging()
    logger = structlog.get_logger("seed")
    if settings.ENVIRONMENT == "production":
        raise SystemExit("禁止在生产环境运行种子脚本，请使用 alembic + 后台 CRUD")
    if settings.AUTO_CREATE_TABLES:
        init_db()
    with SessionLocal() as db:
        bootstrap_data(db)
    logger.info("seed_done")


if __name__ == "__main__":
    main()
