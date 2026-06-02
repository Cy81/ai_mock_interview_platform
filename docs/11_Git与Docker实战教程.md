# Git 与 Docker 实战教程

本章面向第一次把项目提交到 Git 仓库、并用 Docker 启动完整服务的学习者。目标不是背命令，而是知道每条命令在解决什么问题，遇到报错时能判断下一步该看哪里。

## 一、Git 是什么

Git 是版本控制工具。它负责记录代码每一次变更，让你可以：

- 查看改了哪些文件；
- 保存一个稳定版本；
- 回退错误修改；
- 和别人协作开发；
- 把本地项目推送到 GitHub、Gitee、GitLab 等远程仓库。

常见概念：

| 名词 | 含义 |
| --- | --- |
| 工作区 | 你正在编辑的项目文件 |
| 暂存区 | 准备放进下一次提交的文件清单 |
| 提交 | 一次有说明的代码快照 |
| 分支 | 一条独立的开发线 |
| 远程仓库 | GitHub/Gitee/GitLab 上的仓库 |
| main | 常用主分支名 |

## 二、第一次配置 Git

安装 Git 后，先配置用户名和邮箱。它们会写进提交记录里。

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

查看配置：

```bash
git config --global --list
```

## 三、把本项目交给 Git 管理

进入项目根目录：

```bash
cd D:\编程\python学习\实战项目\ai_mock_interview_platform
```

初始化仓库：

```bash
git init -b main
```

查看状态：

```bash
git status
```

把文件加入暂存区：

```bash
git add .
```

创建提交：

```bash
git commit -m "Initial commit"
```

查看最近一次提交：

```bash
git log --oneline -1
```

## 四、.gitignore 的作用

不是所有文件都应该提交。下面这些通常不要进入仓库：

- `.env`：真实密钥、数据库密码、API Key；
- `node_modules/`：前端依赖目录；
- `dist/`：前端构建产物；
- `__pycache__/`、`*.pyc`：Python 缓存；
- `*.db`：本地数据库；
- `*.log`：日志文件；
- `.venv/`、`venv/`：Python 虚拟环境。

本项目的 `.gitignore` 已经覆盖这些常见本地产物。提交前可以检查忽略效果：

```bash
git status --short --ignored
```

以 `!!` 开头的是被忽略的文件，以 `??` 开头的是未跟踪文件。

## 五、推送到 GitHub

先在 GitHub 创建一个空仓库，例如：

```text
https://github.com/Cy81/ai_mock_interview_platform
```

然后在本地项目中添加远程仓库：

```bash
git remote add origin https://github.com/Cy81/ai_mock_interview_platform.git
```

查看 remote：

```bash
git remote -v
```

推送 main 分支：

```bash
git push -u origin main
```

`-u` 会把本地 `main` 和远程 `origin/main` 关联起来。之后再推送只需要：

```bash
git push
```

## 六、日常 Git 工作流

每天开发时常用这套顺序：

```bash
git status
git pull

# 修改代码

git status
git add .
git commit -m "说明这次改了什么"
git push
```

写提交信息时，建议说明业务含义，不要只写 `update`。

较好的例子：

```bash
git commit -m "Fix auth request body parsing"
git commit -m "Add Docker deployment guide"
git commit -m "Improve job recommendation empty state"
```

## 七、分支的基本用法

创建并切换到新分支：

```bash
git switch -c feature/docker-guide
```

查看当前分支：

```bash
git branch
```

切回主分支：

```bash
git switch main
```

合并功能分支：

```bash
git merge feature/docker-guide
```

删除已经合并的分支：

```bash
git branch -d feature/docker-guide
```

建议：主分支保持稳定，新功能放到单独分支开发。

## 八、常见 Git 报错

### 1. 不是 Git 仓库

报错：

```text
fatal: not a git repository
```

原因：当前目录没有 `.git`。

处理：

```bash
git init -b main
```

或者进入正确项目目录。

### 2. 没有 remote

报错：

```text
No configured push destination
```

处理：

```bash
git remote add origin 仓库地址
git push -u origin main
```

### 3. GitHub 连接失败

报错：

```text
Failed to connect to github.com port 443
```

优先检查：

- 网络是否能访问 GitHub；
- 代理是否开启；
- GitHub 仓库是否已经创建；
- 仓库地址是否写错。

### 4. 认证失败

报错可能包含：

```text
Authentication failed
Permission denied
```

处理方向：

- HTTPS 推送需要 GitHub Token 或浏览器登录凭据；
- SSH 推送需要配置 SSH Key；
- 确认当前账号对仓库有写权限。

## 九、Docker 是什么

Docker 用容器运行服务。容器可以理解成一个轻量、可复制的运行环境。

常见概念：

| 名词 | 含义 |
| --- | --- |
| Image | 镜像，应用运行环境模板 |
| Container | 容器，由镜像启动出来的进程 |
| Dockerfile | 构建镜像的说明书 |
| Volume | 数据卷，用来持久化数据 |
| Network | 容器之间通信的网络 |
| Docker Compose | 用一个 YAML 文件编排多个容器 |

本项目不是单服务应用，它至少包含：

- PostgreSQL + pgvector；
- Redis；
- FastAPI 后端；
- Celery worker；
- Celery beat；
- Vue 前端；
- Nginx 网关。

所以更适合用 Docker Compose 一次性启动。

## 十、本项目 Docker Compose 启动

进入项目根目录：

```bash
cd D:\编程\python学习\实战项目\ai_mock_interview_platform
```

复制环境变量模板：

```bash
copy .env.example .env
```

启动并构建：

```bash
docker compose up --build
```

后台启动：

```bash
docker compose up -d --build
```

查看服务状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs
```

持续跟踪日志：

```bash
docker compose logs -f
```

只看后端日志：

```bash
docker compose logs -f backend
```

停止服务：

```bash
docker compose down
```

停止并删除数据卷：

```bash
docker compose down -v
```

注意：`down -v` 会删除 PostgreSQL 数据卷，数据库里的数据会丢失。

## 十一、项目服务访问地址

Docker Compose 启动后，常用访问地址：

| 服务 | 地址 |
| --- | --- |
| Nginx 统一入口 | http://127.0.0.1 |
| 后端 API | http://127.0.0.1:8000 |
| Swagger | http://127.0.0.1:8000/docs |
| 前端直连 | http://127.0.0.1:5173 |
| PostgreSQL | 127.0.0.1:5432 |
| Redis | 127.0.0.1:6379 |

生产访问建议走 Nginx 统一入口，本地调试可以直接访问后端或前端端口。

## 十二、常用 Docker 命令

查看本机镜像：

```bash
docker images
```

查看运行中的容器：

```bash
docker ps
```

查看所有容器：

```bash
docker ps -a
```

进入后端容器：

```bash
docker compose exec backend sh
```

在后端容器里执行迁移：

```bash
docker compose exec backend alembic upgrade head
```

在后端容器里运行测试：

```bash
docker compose exec backend python -m pytest
```

重新构建某个服务：

```bash
docker compose build backend
```

重启某个服务：

```bash
docker compose restart backend
```

## 十三、Dockerfile 怎么读

一个典型后端 Dockerfile 会做这些事：

1. 选择 Python 基础镜像；
2. 设置工作目录；
3. 复制依赖文件；
4. 安装依赖；
5. 复制项目源码；
6. 暴露端口；
7. 设置启动命令。

一个典型前端 Dockerfile 会做这些事：

1. 用 Node 镜像构建 Vue 项目；
2. 执行 `npm install`；
3. 执行 `npm run build`；
4. 用 Nginx 镜像托管 `dist` 静态文件。

重点：镜像构建阶段和容器运行阶段不是一回事。构建阶段生成环境，运行阶段启动服务。

## 十四、Docker Compose 文件怎么读

本项目的 `docker-compose.yml` 核心结构是：

```yaml
services:
  postgres:
  redis:
  backend:
  celery_worker:
  celery_beat:
  frontend:
  nginx:

volumes:
  postgres_data:
```

关注几个字段：

| 字段 | 含义 |
| --- | --- |
| `image` | 直接使用现成镜像 |
| `build` | 使用本地 Dockerfile 构建镜像 |
| `ports` | 宿主机端口映射到容器端口 |
| `volumes` | 挂载文件或数据卷 |
| `env_file` | 读取环境变量文件 |
| `depends_on` | 服务启动依赖 |
| `command` | 覆盖容器默认启动命令 |
| `restart` | 容器异常退出后的重启策略 |

## 十五、Docker 常见问题

### 1. 端口被占用

报错可能包含：

```text
port is already allocated
```

处理：

```bash
docker ps
```

找到占用端口的容器后停止：

```bash
docker stop 容器ID
```

或者修改 `docker-compose.yml` 的左侧宿主机端口。

### 2. 后端连不上数据库

检查：

```bash
docker compose ps
docker compose logs postgres
docker compose logs backend
```

确认 `.env` 里的 `DATABASE_URL` 指向 Compose 服务名 `postgres`，不是 `localhost`。

容器内部访问另一个服务时，应该使用服务名：

```text
postgres:5432
redis:6379
```

### 3. 修改代码后没有生效

如果是镜像内代码，需要重新构建：

```bash
docker compose up -d --build
```

如果只是容器状态异常，可以重启：

```bash
docker compose restart backend
```

### 4. 磁盘占用越来越大

清理停止的容器、悬空镜像和构建缓存：

```bash
docker system prune
```

更彻底清理未使用数据卷：

```bash
docker system prune --volumes
```

谨慎使用带 `--volumes` 的清理命令，因为它可能删除数据库数据卷。

## 十六、推荐练习顺序

1. 用 Git 初始化项目并创建一次提交；
2. 在 GitHub 创建远程仓库；
3. 执行 `git remote add origin ...`；
4. 执行 `git push -u origin main`；
5. 修改一个文档文件；
6. 再执行 `git status`、`git add .`、`git commit`、`git push`；
7. 用 `docker compose up -d --build` 启动完整项目；
8. 用 `docker compose logs -f backend` 查看后端启动日志；
9. 访问 Swagger 和前端页面；
10. 用 `docker compose down` 停止服务。

完成这 10 步后，就已经掌握了企业项目最常用的 Git 与 Docker 基础工作流。

