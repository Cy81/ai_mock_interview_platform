.PHONY: help up down build logs ps migrate seed test lint fmt clean

# ─── 默认目标 ─────────────────────────────────────────────
help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ─── Docker Compose ───────────────────────────────────────
up: ## 启动全部服务（后台）
	docker compose up -d --build

down: ## 停止并移除容器
	docker compose down

build: ## 仅构建镜像
	docker compose build

logs: ## 查看日志（跟踪模式）
	docker compose logs -f --tail=100

ps: ## 查看服务状态
	docker compose ps

# ─── 后端开发 ─────────────────────────────────────────────
migrate: ## 执行数据库迁移
	cd backend && alembic upgrade head

seed: ## 运行种子数据
	cd backend && python scripts/seed_data.py

test: ## 运行后端测试
	cd backend && python -m pytest tests/ -v --tb=short

lint: ## 后端代码检查
	cd backend && python -m ruff check app/ tests/

fmt: ## 后端代码格式化
	cd backend && python -m ruff format app/ tests/

# ─── 前端开发 ─────────────────────────────────────────────
fe-dev: ## 启动前端开发服务器
	cd frontend && npm run dev

fe-build: ## 构建前端生产包
	cd frontend && npm run build

fe-lint: ## 前端代码检查
	cd frontend && npm run lint

# ─── 清理 ─────────────────────────────────────────────────
clean: ## 清理 Docker 卷和构建缓存
	docker compose down -v
	docker system prune -f
