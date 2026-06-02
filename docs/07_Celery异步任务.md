# 07 Celery 异步任务：生产级任务编排

## 学习目标

| 维度 | 达标标准 |
|------|----------|
| 架构理解 | 能画出 API → Redis Broker → Worker → DB 的异步链路 |
| 生产配置 | 掌握 acks_late / reject_on_worker_lost / soft_time_limit 的含义 |
| 重试策略 | 理解 autoretry_for + retry_backoff + max_retries 的组合 |
| 队列路由 | 能为不同任务类型配置独立队列并按需扩容 |
| 幂等设计 | 理解 content_hash 去重如何保证任务重试安全 |

## 一、为什么需要异步任务

### 1.1 同步阻塞的问题

```text
用户上传 RAG 文档 → HTTP 请求
  → 文档切分（~100ms）
  → 调用 Embedding API（~3-10s，可能超时）
  → 写入 pgvector（~200ms）
  → 返回响应

总耗时：4-12 秒 → 用户等待 → 连接池占用 → 超时风险
```

### 1.2 异步化后的架构

```text
用户上传 → HTTP 请求
  → 写入 RagDocument（status=pending）
  → 发送 Celery 任务到 Redis
  → 立即返回 202 Accepted（~50ms）

Worker 异步处理：
  → 取任务 → 切分 → Embedding → 写入 chunks → 更新 status=completed
  → 失败 → 重试 → 最终失败 → status=failed + 告警
```

## 二、Celery 生产配置

### 2.1 核心配置（app/tasks/celery_app.py）

```python
celery_app = Celery("aimi")
celery_app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,

    # 可靠性
    task_acks_late=True,              # 任务完成后才 ACK
    task_reject_on_worker_lost=True,  # Worker 崩溃时任务回队列
    broker_connection_retry_on_startup=True,

    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 队列路由
    task_routes={
        "app.tasks.indexing.*": {"queue": "indexing"},
        "app.tasks.scoring.*": {"queue": "scoring"},
    },

    # 性能
    worker_prefetch_multiplier=1,     # 一次只取一个任务（配合 acks_late）
    worker_max_tasks_per_child=200,   # 防止内存泄漏
)
```

### 2.2 关键参数解释

| 参数 | 值 | 作用 |
|------|-----|------|
| task_acks_late | True | 任务执行完才确认，崩溃时不丢任务 |
| task_reject_on_worker_lost | True | Worker 被 kill 时任务重新入队 |
| worker_prefetch_multiplier | 1 | 配合 acks_late，避免预取后崩溃丢多个任务 |
| worker_max_tasks_per_child | 200 | 执行 200 个任务后重启进程，防止内存泄漏 |
| task_serializer="json" | — | 避免 pickle 安全风险 |

## 三、索引任务实现

### 3.1 任务定义（app/tasks/indexing.py）

```python
@celery_app.task(
    bind=True,                          # self 参数，可访问 task 元信息
    autoretry_for=(Exception,),         # 所有异常自动重试
    retry_backoff=True,                 # 指数退避
    retry_backoff_max=300,              # 最大退避 5 分钟
    max_retries=3,                      # 最多重试 3 次
    soft_time_limit=180,                # 软超时 3 分钟（抛 SoftTimeLimitExceeded）
    acks_late=True,                     # 完成后才 ACK
)
def index_rag_document(self, document_id: int):
    """异步索引 RAG 文档：切分 → Embedding → 写入 chunks"""
    with session_scope() as db:
        doc = db.get(RagDocument, document_id)
        if not doc:
            return {"status": "not_found"}

        doc.index_status = IndexStatus.INDEXING
        db.commit()

        try:
            chunks = split_document(doc)
            embeddings = embed_batch([c.content for c in chunks])
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb
                db.add(chunk)
            doc.index_status = IndexStatus.COMPLETED
            db.commit()
            return {"status": "completed", "chunks": len(chunks)}
        except SoftTimeLimitExceeded:
            doc.index_status = IndexStatus.FAILED
            db.commit()
            raise
        except Exception:
            doc.index_status = IndexStatus.FAILED
            db.commit()
            raise  # autoretry_for 会捕获并重试
```

### 3.2 重试时序

```text
第 1 次执行 → 失败（如 Embedding API 超时）
  → 等待 ~2s（retry_backoff）
第 2 次重试 → 失败
  → 等待 ~4s
第 3 次重试 → 失败
  → 等待 ~8s
第 4 次（max_retries=3 已用完）→ 最终失败 → 任务进入 dead letter
```

### 3.3 幂等保证

```python
# content_hash 去重：即使任务重试，不会产生重复 chunks
existing = db.query(RagChunk).filter_by(document_id=doc.id).count()
if existing > 0:
    # 已有 chunks，先清除再重建（幂等）
    db.query(RagChunk).filter_by(document_id=doc.id).delete()
```

## 四、评分任务

### 4.1 异步评分（app/tasks/scoring.py）

```python
@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=120,
)
def score_interview_async(self, interview_id: int):
    """异步评分：适用于大批量或高并发场景"""
    with session_scope() as db:
        interview = db.get(Interview, interview_id)
        interview.status = InterviewStatus.SCORING
        db.commit()
        # ... 调用 AI Provider 生成报告 ...
```

## 五、队列路由与扩容

### 5.1 Docker Compose 配置

```yaml
celery_worker:
  command: >
    celery -A app.tasks.celery_app.celery_app worker
      -Q indexing,scoring
      --loglevel=INFO
      --concurrency=2
      --max-tasks-per-child=200

celery_beat:
  command: >
    celery -A app.tasks.celery_app.celery_app beat
      --loglevel=INFO
```

### 5.2 按队列独立扩容

```bash
# 索引队列压力大时，单独加 Worker
docker compose up -d --scale celery_worker=3

# 或者启动专用 scoring Worker
celery -A app.tasks.celery_app.celery_app worker -Q scoring --concurrency=4
```

## 六、监控与可观测

### 6.1 Flower 监控面板

```bash
celery -A app.tasks.celery_app.celery_app flower --port=5555
```

可观测：
- 活跃/已完成/失败任务数
- 每个 Worker 的负载
- 任务执行耗时分布
- 重试次数统计

### 6.2 structlog 任务日志

```python
@celery_app.task(bind=True, ...)
def index_rag_document(self, document_id):
    logger.info("task.started", task_id=self.request.id, document_id=document_id)
    # ...
    logger.info("task.completed", task_id=self.request.id, chunks=len(chunks))
```

## 实验步骤

1. 启动 Redis + Worker：`docker compose up redis celery_worker -d`
2. 通过管理后台上传一份 RAG 文档，观察 Worker 日志
3. 在 Worker 日志中确认 `task.started` → `task.completed`
4. 故意设置错误的 Embedding API Key，观察重试行为
5. 用 `celery inspect active` 查看当前执行中的任务
6. 启动 Flower：`celery flower`，在浏览器查看任务统计

## 考核标准

| 等级 | 要求 |
|------|------|
| 及格 | 能解释 acks_late 的作用，能说出异步化的好处 |
| 良好 | 能配置新的任务队列，能解释重试策略各参数含义 |
| 优秀 | 能设计幂等任务，能实现任务状态追踪并暴露给前端 |

## 练习任务

1. 新增一个 `send_notification` 任务，放入 `notification` 队列
2. 给 `index_rag_document` 添加进度上报（通过 `self.update_state`）
3. 实现一个定时任务（Celery Beat）：每小时清理 `failed` 状态超过 24h 的文档
4. 设计一个前端轮询方案：上传文档后每 2s 查询索引状态直到完成
5. 思考：如果 Worker 在写入 chunks 到一半时崩溃，如何保证数据一致性？
