# 03 数据库与 pgvector：企业级数据建模

## 学习目标

| 维度 | 达标标准 |
|------|----------|
| 模型设计 | 能说出 8 张表的关系与拆分理由（Interview 三表拆分） |
| pgvector | 理解 Vector 列、HNSW 索引参数（m/ef_construction）、cosine_distance 算子 |
| 连接池 | 掌握 pool_size/max_overflow/recycle/pool_use_lifo 的生产配置 |
| Alembic | 能独立编写迁移脚本，理解 native_enum=False 的跨库兼容策略 |

## 一、数据模型全景

```text
users ─────────┬──── resumes
               │
               ├──── interviews ──── interview_questions
               │                └─── interview_answers
               │
job_directions ─┘

rag_documents ──── rag_chunks (embedding Vector)
```

### 1.1 八张核心表

| 表 | 核心字段 | 设计要点 |
|----|----------|----------|
| users | email, role(enum), failed_login_attempts, locked_until | 失败锁定策略 |
| resumes | raw_text, parsed_profile(JSON), content_hash, parse_status(enum) | 幂等解析 |
| job_directions | code(unique), required_skills(JSON), competency_model(JSON) | 能力模型驱动 |
| interviews | status(enum), idempotency_key(unique), overall_score | 状态机 + 幂等 |
| interview_questions | position, type(enum), difficulty(enum), rubric(JSON) | 有序子表 |
| interview_answers | question_id(unique per interview), duration_ms, score | 覆盖式提交 |
| rag_documents | rag_type(enum), content_hash, index_status(enum) | 去重 + 状态追踪 |
| rag_chunks | document_id(FK), embedding(Vector), chunk_index | 向量检索单元 |

### 1.2 Interview 三表拆分的理由

旧设计把 questions/answers 放在 Interview 的 JSON 字段里，导致：
- 无法对单题做索引查询
- 无法记录每题作答时长
- 评分回写需要解析整个 JSON

拆分后每张子表有独立主键，支持：
- `UniqueConstraint("interview_id", "position")` 保证题序唯一
- `UniqueConstraint("question_id")` on answer 保证一题一答（覆盖式）
- 逐题评分直接 UPDATE answer.score

## 二、SQLAlchemy 2.x 模式

### 2.1 Base + TimestampMixin

```python
# app/db/base.py
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

class Base(DeclarativeBase):
    pass
```

所有业务表继承 `Base` 并 mixin `TimestampMixin`，确保时间戳由数据库生成（`server_default`），避免应用时钟偏差。

### 2.2 枚举策略：native_enum=False

```python
class InterviewStatus(str, Enum):
    CREATED = "created"
    GENERATING = "generating"
    IN_PROGRESS = "in_progress"
    ...

status: Mapped[InterviewStatus] = mapped_column(
    SAEnum(InterviewStatus, native_enum=False)
)
```

`native_enum=False` 使枚举存储为 VARCHAR，好处：
- SQLite 测试兼容（SQLite 无 ENUM 类型）
- 新增枚举值无需 ALTER TYPE 迁移
- 跨数据库可移植

## 三、pgvector 与 HNSW 索引

### 3.1 Vector 列定义

```python
# app/models/rag.py
from pgvector.sqlalchemy import Vector

class RagChunk(Base):
    embedding = mapped_column(Vector(settings.EMBEDDING_DIMENSIONS))
```

### 3.2 HNSW 索引创建（Alembic 迁移）

```sql
-- 仅 PostgreSQL 执行
CREATE INDEX ix_rag_chunks_embedding_hnsw
ON rag_chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

| 参数 | 含义 | 推荐值 |
|------|------|--------|
| m | 每个节点的最大连接数 | 16（平衡精度与内存） |
| ef_construction | 构建时搜索宽度 | 64（越大越精确，构建越慢） |
| vector_cosine_ops | 距离算子 | 余弦距离（归一化向量） |

### 3.3 检索查询

```python
# app/services/rag_service.py
distance = RagChunk.embedding.cosine_distance(query_vector).label("distance")
stmt = (
    select(RagChunk, distance)
    .where(RagChunk.document_id.in_(active_doc_ids))
    .order_by(distance)
    .limit(top_k)
)
```

## 四、连接池配置

```python
# app/db/session.py
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,          # 常驻连接数
    max_overflow=10,       # 突发可额外创建
    pool_recycle=1800,     # 30分钟回收（防止 PG 断开空闲连接）
    pool_use_lifo=True,    # 后进先出，减少活跃连接数
    pool_pre_ping=True,    # 取连接前 ping 一次
)
```

SQLite 测试模式使用 `StaticPool`（单连接共享），避免多线程锁问题。

## 五、Alembic 迁移实践

### 5.1 迁移文件结构

```text
alembic/
├── env.py          # 导入所有 models，compare_type=True
├── versions/
│   └── 0001_initial.py   # 8 表 + 7 枚举 + HNSW 索引
└── alembic.ini
```

### 5.2 关键技巧

- `server_default=func.now()` 而非 `default=datetime.utcnow`（数据库时钟权威）
- HNSW 索引用 `op.execute()` 原生 SQL，仅在 PostgreSQL dialect 下执行
- `native_enum=False` 避免 `CREATE TYPE` / `DROP TYPE` 的迁移复杂度

## 实验步骤

1. 查看 `backend/app/models/` 下所有模型文件，画出 ER 图
2. 启动 PostgreSQL：`docker compose up postgres -d`
3. 执行迁移：`cd backend && alembic upgrade head`
4. 连接数据库验证表结构：`psql -U interview -d interview -c '\dt'`
5. 验证 HNSW 索引：`\di ix_rag_chunks_embedding_hnsw`

## 考核标准

| 等级 | 要求 |
|------|------|
| 及格 | 能说出 8 张表的关系，理解 Interview 三表拆分的理由 |
| 良好 | 能解释 HNSW 参数含义，能独立编写新字段的 Alembic 迁移 |
| 优秀 | 能设计一个新业务表（如"学习计划跟踪"），编写完整迁移并通过测试 |

## 练习任务

1. 给 `users` 表新增 `phone` 字段，编写 Alembic 迁移并执行
2. 修改 `EMBEDDING_DIMENSIONS` 为 768，观察会发生什么
3. 用 `EXPLAIN ANALYZE` 对比有无 HNSW 索引的向量检索性能
4. 思考：如果要支持多租户，哪些表需要加 `tenant_id`？
