# AI 模拟面试系统企业实战课程

这是一个面向求职场景的 AI 应用实战项目。课程从业务闭环出发，把简历解析、岗位匹配 Agent、题库 RAG、知识库 RAG、模拟面试、评分报告、前端工作台、异步任务、测试和部署串成一套可运行的软件系统。

项目默认使用 Mock 模式，学习者不需要 API Key 就能跑通全流程；需要接入真实模型时，可通过环境变量切换到 DeepSeek 与 DashScope。

## 技术栈

后端：

- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- pgvector
- Redis
- Celery
- DeepSeek OpenAI Compatible API
- DashScope Embedding
- pytest

前端：

- Vue 3
- Vite
- Pinia
- Vue Router
- Axios
- lucide-vue-next
- Nginx

## 项目结构

```text
ai_mock_interview_platform/
  backend/     FastAPI API、领域服务、模型、任务、测试、迁移
  frontend/    Vue 3 企业后台工作台
  docs/        企业实战课程分章文档
  nginx/       生产反向代理配置
  output/      Playwright 截图和验证输出
```

核心业务链路：

```text
注册登录
  -> 简历文本/文件解析
  -> 候选人画像
  -> 岗位匹配 Agent
  -> 题库 RAG 生成面试题
  -> 候选人答题
  -> 知识库 RAG 辅助评分
  -> 评分报告和学习计划
```

## 快速启动：后端 Mock 模式

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问：

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## 快速启动：前端

```bash
cd frontend
cmd /c npm install
cmd /c npm run dev
```

访问 http://127.0.0.1:5173。

默认可以直接注册 `demo@example.com / demo123456`，也可以使用任意邮箱注册新用户。

## Docker Compose

```bash
copy .env.example .env
docker compose up --build
```

服务说明：

- `postgres`: PostgreSQL + pgvector
- `redis`: Celery broker/backend
- `backend`: FastAPI API
- `celery_worker`: RAG 文档异步索引 Worker
- `frontend`: Vue 静态站点
- `nginx`: 统一入口和反向代理

## 真实模型配置

`.env.example` 默认是 Mock：

```env
AI_RUNTIME=mock
EMBEDDING_RUNTIME=mock
```

切换真实模型：

```env
AI_RUNTIME=deepseek
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

EMBEDDING_RUNTIME=dashscope
DASHSCOPE_API_KEY=你的 DashScope Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
```

注意：`EMBEDDING_DIMENSIONS` 必须和 pgvector 字段维度、Embedding 模型输出维度保持一致。

## 主要 API

- `POST /api/v1/auth/register`: 注册并返回 JWT
- `POST /api/v1/auth/login`: 登录并返回 JWT
- `POST /api/v1/resumes/text`: 录入文本简历
- `POST /api/v1/resumes/upload`: 上传 PDF、DOCX、TXT、Markdown 简历
- `POST /api/v1/jobs/recommend`: 根据简历推荐岗位方向
- `POST /api/v1/rag/documents`: 写入题库 RAG 或知识库 RAG
- `POST /api/v1/rag/documents/search`: 检索 RAG 文档
- `POST /api/v1/interviews`: 创建模拟面试
- `POST /api/v1/interviews/{id}/answers`: 提交回答
- `POST /api/v1/interviews/{id}/finish`: 完成面试并生成评分报告
- `GET /api/v1/reports/{interview_id}`: 获取评分报告

接口错误语义：

- `401`: 未登录、Token 无效或过期
- `404`: 资源不存在或无权限访问
- `409`: 当前业务状态不允许操作，例如报告尚未生成
- `422`: 请求参数校验失败

## 测试

后端：

```bash
cd backend
python -m pytest
```

前端：

```bash
cd frontend
cmd /c npm run build
```

建议课堂验收主流程：

1. 注册或登录。
2. 录入一份包含 Python、FastAPI、RAG、Docker 等关键词的简历。
3. 生成岗位推荐。
4. 创建一场模拟面试。
5. 提交至少一道题的回答。
6. 完成面试并查看评分报告。
7. 在 RAG 管理中新增题库或知识库文档并检索。

## 学习路径

按 `docs/` 目录阅读：

1. `01_导学.md`: 项目目标、业务闭环和课程节奏
2. `02_架构设计.md`: 前后端、数据库、RAG、Agent、异步任务架构
3. `03_数据库与pgvector.md`: 表结构、迁移、向量字段和检索策略
4. `04_AI_Provider.md`: Mock、DeepSeek、结构化 JSON 输出
5. `05_双RAG设计.md`: 题库 RAG 与知识库 RAG 的职责边界
6. `06_岗位匹配Agent.md`: 可解释匹配分、能力差距和学习路径
7. `07_Celery异步任务.md`: RAG 文档索引异步化
8. `08_前端工程.md`: Vue 企业后台页面组织
9. `09_部署与测试.md`: 测试、构建、Docker 和生产检查清单
10. `10_扩展作业.md`: 可继续迭代的企业级功能
