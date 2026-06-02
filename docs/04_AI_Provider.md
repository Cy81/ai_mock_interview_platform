# 04 AI Provider：生产级 LLM 调用工程

## 学习目标

| 维度 | 达标标准 |
|------|----------|
| 抽象设计 | 理解 Provider 模式如何隔离业务与模型厂商 |
| 容错机制 | 掌握 tenacity 指数退避重试 + httpx.Timeout 的配置 |
| JSON Mode | 理解 response_format={"type":"json_object"} 的作用与限制 |
| 流式输出 | 能实现 SSE 流式返回 token 的完整链路 |
| Mock 测试 | 理解 MockProvider 在 CI 和开发中的价值 |

## 一、Provider 抽象架构

```text
┌─────────────────────────────────────────┐
│           业务 Service 层                │
│  resume_parser / interview_service      │
└──────────────┬──────────────────────────┘
               │ 调用
       ┌───────▼───────┐
       │  AI Provider   │  ← 统一接口
       │  (抽象层)      │
       └───┬───────┬───┘
           │       │
    ┌──────▼──┐ ┌──▼──────────┐
    │  Mock   │ │ DeepSeek    │
    │Provider │ │ Provider    │
    └─────────┘ └─────────────┘
```

### 核心接口

```python
class LLMResponse:
    content: str          # 模型输出文本
    usage: LLMUsage       # token 用量
    latency_ms: int       # 调用耗时
    model: str            # 实际使用的模型

# 两个核心方法
chat_json(system, user_prompt) → LLMResponse   # 强制 JSON 输出
chat_stream(system, user_prompt) → Iterator[str]  # 流式 token
```

## 二、DeepSeek Provider 实现

### 2.1 配置项（app/core/config.py）

```python
AI_RUNTIME: str = "mock"           # mock / deepseek
AI_API_KEY: str = ""
AI_BASE_URL: str = "https://api.deepseek.com"
AI_MODEL: str = "deepseek-chat"
AI_TEMPERATURE: float = 0.3
AI_TIMEOUT: int = 60               # 秒
AI_MAX_RETRIES: int = 3
```

### 2.2 tenacity 重试策略

```python
@retry(
    stop=stop_after_attempt(settings.AI_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def chat_json(self, system: str, user_prompt: str) -> LLMResponse:
    ...
```

| 参数 | 含义 |
|------|------|
| stop_after_attempt(3) | 最多重试 3 次 |
| wait_exponential(min=2, max=30) | 2s → 4s → 8s...最大 30s |
| retry_if_exception_type | 仅对超时和 5xx 重试，4xx 不重试 |

### 2.3 JSON Mode 强制结构化

```python
response = await client.chat.completions.create(
    model=settings.AI_MODEL,
    messages=[...],
    temperature=settings.AI_TEMPERATURE,
    response_format={"type": "json_object"},  # 关键！
    stream_options={"include_usage": True},
)
```

**为什么需要 JSON Mode？**
- 防止模型输出 Markdown 包裹的 JSON（```json ... ```）
- 防止模型输出额外解释文字
- 配合 Pydantic 解析，失败时有明确错误

### 2.4 流式输出（SSE）

```python
def chat_stream(self, system: str, user_prompt: str) -> Iterator[str]:
    with httpx.stream("POST", ...) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                chunk = json.loads(line[6:])
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
```

前端通过 `EventSource` 或 `fetch` 消费 SSE 流，实现打字机效果。

## 三、Embedding Provider

### 3.1 DashScope 批量调用

```python
class DashScopeEmbeddingProvider:
    BATCH_LIMIT = 10  # DashScope 单次最多 10 条

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(...))
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # 按 BATCH_LIMIT 分批
        for batch in chunked(texts, self.BATCH_LIMIT):
            response = await self.client.post(...)
            results.extend(response["output"]["embeddings"])
        return results
```

### 3.2 余弦相似度（Python fallback）

```python
def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_np, b_np = np.array(a), np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))
```

SQLite 测试环境无 pgvector，用 Python 计算代替。

## 四、Mock Provider

```python
class MockAIProvider:
    def chat_json(self, system, user_prompt):
        # 根据 prompt 中的关键词返回固定 JSON
        return LLMResponse(
            content=json.dumps(mock_result),
            usage=LLMUsage(prompt_tokens=100, completion_tokens=200),
            latency_ms=50,
            model="mock",
        )
```

Mock 的价值：
1. **CI 测试**：不依赖外部网络，结果可预测
2. **前端开发**：后端秒级响应，不被 AI 延迟阻塞
3. **课程教学**：零成本跑通全流程

## 五、切换配置

```env
# Mock 模式（默认）
AI_RUNTIME=mock
EMBEDDING_RUNTIME=mock

# 真实模式
AI_RUNTIME=deepseek
AI_API_KEY=sk-xxx
EMBEDDING_RUNTIME=dashscope
EMBEDDING_API_KEY=sk-xxx
```

`get_ai_provider()` 工厂函数根据 `AI_RUNTIME` 返回对应实例。

## 六、生产化要点

| 要点 | 做法 |
|------|------|
| 超时控制 | httpx.Timeout(connect=10, read=AI_TIMEOUT) |
| 重试幂等 | chat_json 是无副作用的，可安全重试 |
| 用量追踪 | LLMResponse.usage 记录 token 消耗 |
| 延迟监控 | LLMResponse.latency_ms 上报 Prometheus |
| 密钥安全 | 仅从环境变量读取，不入代码仓库 |
| 降级策略 | AI 失败时 interview 状态设为 FAILED + status_reason |

## 实验步骤

1. Mock 模式下创建面试，观察返回的题目结构
2. 修改 `.env` 切换到 `AI_RUNTIME=deepseek`（需要 API Key）
3. 再次创建面试，对比真实模型输出与 Mock 的差异
4. 故意设置错误的 API Key，观察重试日志和最终错误响应
5. 调用 SSE 流式接口 `GET /interviews/{id}/answer/stream`

## 考核标准

| 等级 | 要求 |
|------|------|
| 及格 | 能解释 Provider 模式的好处，能切换 Mock/真实模式 |
| 良好 | 能说明 tenacity 重试参数的含义，能解释 JSON Mode 的必要性 |
| 优秀 | 能新增一个 Provider（如 OpenAI/Qwen），并通过现有测试 |

## 练习任务

1. 阅读 `app/services/ai_provider.py`，画出 `chat_json` 的完整调用链
2. 修改 Mock Provider 的评分逻辑，增加"代码规范"维度
3. 给 `chat_json` 添加调用耗时的 structlog 日志
4. 实现一个 `QwenProvider`，接入通义千问 API
