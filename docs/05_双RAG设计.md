# 05 双RAG设计：文档与分块的分离架构

## 学习目标

| 编号 | 目标 | 层级 | 验证方式 |
|------|------|------|----------|
| 1 | 理解 RagDocument + RagChunk 分离模型的设计动机 | 理解 | 能画出 ER 关系图 |
| 2 | 掌握 content_hash 去重机制 | 应用 | 实现 upsert 逻辑 |
| 3 | 区分 RagType 枚举的两种用途 | 理解 | 能说明 question_bank 与 knowledge_base 的区别 |
| 4 | 掌握 DashScope Embedding 批量调用与重试策略 | 应用 | 配置 tenacity 重试参数 |
| 5 | 理解 pgvector 余弦距离搜索与 Python 回退方案 | 分析 | 对比两种方案的性能差异 |
| 6 | 掌握 HNSW 索引参数调优原则 | 应用 | 根据数据规模选择合适参数 |

---

## 原理讲解

### 1. 为什么需要双层 RAG 模型？

传统 RAG 系统将文档和向量混在一张表中，导致以下问题：

- 重复文档无法高效检测
- 文档更新时需要重建所有分块向量
- 无法区分文档级元数据与分块级元数据

本项目采用 **Document-Chunk 分离架构**：

```
┌─────────────────────────────────────────────────┐
│                  RagDocument                      │
│  - id (PK)                                       │
│  - title                                         │
│  - content_hash (UNIQUE)  ← 去重关键字段         │
│  - rag_type: RagType                             │
│  - index_status: IndexStatus                     │
│  - metadata (JSONB)                              │
└──────────────────────┬──────────────────────────┘
                       │ 1:N
┌──────────────────────▼──────────────────────────┐
│                  RagChunk                         │
│  - id (PK)                                       │
│  - document_id (FK → RagDocument)                │
│  - chunk_index (顺序号)                          │
│  - content (文本片段)                            │
│  - embedding (vector(1536))                      │
│  - metadata (JSONB)                              │
└─────────────────────────────────────────────────┘
```

### 2. content_hash 去重机制

```python
import hashlib

def compute_content_hash(content: str) -> str:
    """对文档全文计算 SHA-256，用于判断内容是否变更"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
```

**upsert 流程**：

```
上传文档 → 计算 content_hash
    ├─ hash 已存在且 index_status=completed → 跳过（幂等）
    ├─ hash 已存在但 index_status=failed   → 重新触发索引
    └─ hash 不存在 → 插入文档 → 分块 → 生成 embedding → 写入 chunks
```

### 3. RagType 与 IndexStatus 枚举

```python
class RagType(str, Enum):
    question_bank = "question_bank"      # 面试题库：结构化 Q&A
    knowledge_base = "knowledge_base"    # 知识库：技术文档、岗位说明

class IndexStatus(str, Enum):
    pending = "pending"          # 等待索引
    indexing = "indexing"        # 正在生成 embedding
    completed = "completed"      # 索引完成
    failed = "failed"            # 索引失败
```

两种 RagType 的分块策略不同：
- `question_bank`：按 Q&A 对分块，每个问答为一个 chunk
- `knowledge_base`：按固定长度 + 重叠窗口分块（chunk_size=512, overlap=64）

### 4. DashScope Embedding 批量调用

```python
BATCH_LIMIT = 10  # DashScope 单次最多处理 10 条文本

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RequestException, TimeoutError)),
)
async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
    """调用 DashScope text-embedding-v2 接口"""
    response = await self.client.post(
        self.endpoint,
        json={"input": {"texts": texts}, "model": "text-embedding-v2"},
        headers={"Authorization": f"Bearer {self.api_key}"},
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["output"]["embeddings"]]
```

批量处理逻辑：

```
输入 N 条文本
    → 按 BATCH_LIMIT=10 分组
    → 每组调用一次 API（带 tenacity 重试）
    → 合并所有结果返回

示例：25 条文本 → [10, 10, 5] 三批调用
```

### 5. 向量搜索：pgvector vs Python 回退

**pgvector 方案（生产环境）**：

```sql
SELECT id, content, 1 - (embedding <=> :query_vec) AS similarity
FROM rag_chunks
WHERE document_id IN (SELECT id FROM rag_documents WHERE rag_type = :rag_type)
ORDER BY embedding <=> :query_vec
LIMIT :top_k;
```

**Python 回退方案（开发/无 pgvector 环境）**：

```python
from numpy import dot
from numpy.linalg import norm

def cosine_similarity(a, b):
    return dot(a, b) / (norm(a) * norm(b))

def search_fallback(query_embedding, chunks, top_k=5):
    scored = [
        (chunk, cosine_similarity(query_embedding, chunk.embedding))
        for chunk in chunks
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
```

| 方案 | 适用场景 | 时间复杂度 | 召回率 |
|------|----------|-----------|--------|
| pgvector + HNSW | 生产环境，数据量 > 1000 | O(log N) | ~95% |
| Python 回退 | 开发测试，数据量 < 1000 | O(N) | 100%（精确） |

### 6. HNSW 参数调优

```sql
CREATE INDEX idx_rag_chunks_embedding ON rag_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- 查询时设置 ef_search
SET hnsw.ef_search = 100;
```

| 参数 | 含义 | 推荐值 | 权衡 |
|------|------|--------|------|
| m | 每个节点的最大连接数 | 16 | 越大召回越高，内存占用越大 |
| ef_construction | 构建索引时的搜索宽度 | 200 | 越大索引构建越慢，质量越高 |
| ef_search | 查询时的搜索宽度 | 100 | 越大查询越慢，召回率越高 |

**调优建议**：
- 数据量 < 10K：m=16, ef_construction=200
- 数据量 10K-100K：m=32, ef_construction=400
- 数据量 > 100K：m=48, ef_construction=600，考虑分区

---

## 代码导读

### `backend/app/models/rag.py`

| 行范围 | 内容 | 要点 |
|--------|------|------|
| 枚举定义 | `RagType`, `IndexStatus` | 使用 `str, Enum` 确保 JSON 序列化兼容 |
| RagDocument | 文档主表模型 | `content_hash` 字段设置 unique 约束 |
| RagChunk | 分块表模型 | `embedding` 字段使用 pgvector 的 Vector(1536) 类型 |
| 关系定义 | `relationship` | Document → Chunks 一对多，cascade delete |

### `backend/app/services/embedding_provider.py`

| 行范围 | 内容 | 要点 |
|--------|------|------|
| 常量 | `BATCH_LIMIT = 10` | DashScope API 单次上限 |
| `DashScopeEmbeddingProvider` | 主类 | 封装 API 调用细节 |
| `embed_texts` | 批量入口 | 循环按 BATCH_LIMIT 切片，汇总结果 |
| `_call_embedding_api` | 单次调用 | tenacity 装饰器实现指数退避重试 |

### `backend/app/services/rag_service.py`

| 行范围 | 内容 | 要点 |
|--------|------|------|
| `upsert_document` | 文档上传入口 | 先查 hash，存在则跳过或重试 |
| `_split_chunks` | 分块策略 | 根据 rag_type 选择不同分块方式 |
| `_index_document` | 索引流程 | 分块 → embedding → 写入 → 更新状态 |
| `search_similar` | 向量搜索 | 优先 pgvector，异常时回退 Python 计算 |

---

## 实验步骤

### 实验一：观察去重机制

1. 准备一份测试文档（如 `test_doc.txt`，内容为任意技术文章）
2. 调用 `upsert_document` 上传该文档，记录返回的 document_id
3. 再次调用 `upsert_document` 上传完全相同的文档
4. 检查数据库，确认只有一条 RagDocument 记录
5. 修改文档内容一个字符，再次上传，确认生成新记录（新 hash）

### 实验二：对比搜索性能

1. 使用脚本导入 1000 条测试数据到 rag_chunks 表
2. 分别使用 pgvector 搜索和 Python 回退搜索同一查询
3. 使用 `time.perf_counter()` 记录两种方式的响应时间
4. 调整 `hnsw.ef_search` 参数（50/100/200），观察耗时与召回率变化

### 实验三：Embedding 批量与重试

1. 准备 25 条文本，调用 `embed_texts`
2. 观察日志输出，确认分 3 批（10+10+5）调用
3. 使用 `unittest.mock.patch` 模拟第二批 API 超时
4. 观察 tenacity 重试日志，确认指数退避行为（2s → 4s → 失败）

---

## 考核标准

| 等级 | 要求 |
|------|------|
| 及格 | 能说明 Document-Chunk 分离的好处，理解 content_hash 去重原理 |
| 良好 | 能独立实现 upsert_document 逻辑，正确配置 tenacity 重试参数 |
| 优秀 | 能根据数据规模调优 HNSW 参数，能分析并选择 pgvector 与回退方案 |

---

## 练习任务

### 任务一：实现增量更新（难度：中）

当文档内容变更时（hash 不同但 title 相同），不是新增记录，而是：
1. 更新 RagDocument 的 content_hash 和 index_status
2. 删除旧的 RagChunk 记录
3. 重新分块并生成 embedding
4. 确保整个过程在数据库事务中完成

### 任务二：自定义分块策略（难度：低）

为 `knowledge_base` 类型实现基于段落的智能分块：
- 优先按 `\n\n` 分割段落
- 单段落超过 chunk_size 时再按句子切分
- 保证每个 chunk 不超过 512 字符
- 相邻 chunk 有 64 字符重叠

### 任务三：实现多模型 Embedding 支持（难度：高）

扩展 `EmbeddingProvider` 为抽象基类，支持切换：
- DashScope text-embedding-v2（1536 维）
- OpenAI text-embedding-3-small（1536 维）
- 本地 sentence-transformers 模型（384 维）

要求：
- 通过配置文件切换 provider，不修改 rag_service 代码
- 处理不同模型维度不一致的问题（padding 或 projection）
- 编写单元测试验证各 provider 输出格式一致
