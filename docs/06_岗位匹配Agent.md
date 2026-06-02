# 06 岗位匹配Agent：LangChain Tool Calling 模式

## 学习目标

| 编号 | 目标 | 层级 | 验证方式 |
|------|------|------|----------|
| 1 | 理解 Tool Calling 模式与传统 if-else 路由的区别 | 理解 | 能画出两种架构对比图 |
| 2 | 掌握 JobMatchTools 类中三个工具的职责划分 | 应用 | 能独立添加新工具 |
| 3 | 理解 _llm_match 的结构化 JSON 输出设计 | 分析 | 能解释 schema 各字段含义 |
| 4 | 掌握 _rule_match 规则回退机制 | 应用 | 能触发回退并验证结果 |
| 5 | 理解 knowledge_references 的来源追踪设计 | 分析 | 能说明引用如何关联到 RAG 文档 |
| 6 | 区分 source 字段 llm 与 rule 的业务含义 | 理解 | 能根据 source 判断结果可信度 |

---

## 原理讲解

### 1. 为什么选择 Tool Calling 而非 if-else？

传统方案（反模式）：

```python
# 硬编码路由 —— 每新增一种意图就要改代码
if "查岗位" in user_input:
    result = list_jobs()
elif "技能匹配" in user_input:
    result = skill_overlap(user_skills)
elif "知识查询" in user_input:
    result = query_knowledge(user_input)
else:
    result = "无法理解您的需求"
```

Tool Calling 方案：

```
┌──────────────────────────────────────────────────────┐
│                    LLM (决策层)                        │
│  根据用户意图自主选择调用哪些工具、调用顺序、参数      │
└────────┬──────────────┬──────────────┬───────────────┘
         │              │              │
    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
    │list_jobs│   │query_   │   │skill_   │
    │         │   │knowledge│   │overlap  │
    └─────────┘   └─────────┘   └─────────┘
```

**核心优势**：
- LLM 自主决策调用链路，无需预定义所有分支
- 新增工具只需注册，不修改路由逻辑
- 支持多步推理（先查岗位 → 再查知识库 → 最后计算匹配度）
- 工具可组合，同一工具在不同场景下被不同方式调用

### 2. JobMatchTools 三大工具

```python
class JobMatchTools:
    """岗位匹配 Agent 的工具集"""

    @tool("list_jobs")
    def list_jobs(self, filters: dict) -> list[dict]:
        """列出符合条件的岗位列表
        Args:
            filters: {"category": "后端", "level": "P6", "city": "杭州"}
        Returns:
            岗位基本信息列表（code, title, requirements 摘要）
        """
        ...

    @tool("query_knowledge")
    def query_knowledge(self, query: str, job_code: str) -> list[dict]:
        """从 RAG 知识库中检索与岗位相关的技术要求
        Args:
            query: 检索关键词（如 "分布式系统经验要求"）
            job_code: 岗位编码（限定检索范围）
        Returns:
            相关知识片段及来源引用（KnowledgeReference）
        """
        ...

    @tool("skill_overlap")
    def skill_overlap(self, user_skills: list[str], job_code: str) -> dict:
        """计算用户技能与岗位要求的重叠度
        Args:
            user_skills: 用户技能标签列表
            job_code: 目标岗位编码
        Returns:
            {"overlap": [...], "missing": [...], "score": 0.75}
        """
        ...
```

### 3. _llm_match 结构化输出

LLM 被要求返回严格的 JSON Schema：

```json
{
  "recommendations": [
    {
      "code": "BE-P6-001",
      "match_score": 0.82,
      "reasons": [
        "3年 Python 后端经验匹配岗位核心要求",
        "熟悉分布式系统设计，符合技术栈"
      ],
      "gaps": [
        "缺少 Kubernetes 生产环境运维经验",
        "未体现大规模数据处理能力"
      ],
      "suggested_learning_path": [
        "完成 K8s CKA 认证课程",
        "参与公司容器化改造项目积累经验"
      ]
    }
  ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| code | str | 岗位唯一编码，关联 Job 表 |
| match_score | float | 0-1 匹配度，LLM 综合评估 |
| reasons | list[str] | 匹配原因（正向证据） |
| gaps | list[str] | 能力差距（待提升项） |
| suggested_learning_path | list[str] | 针对 gaps 的学习建议 |

### 4. 规则回退机制

```
用户请求 → _llm_match 调用
    ├─ 成功 → 返回 LLM 推荐结果，source="llm"
    └─ 异常（超时 / JSON 解析失败 / API 限流 / 网络错误）
         → 记录异常日志
         → _rule_match 回退，source="rule"
         → 结果仍然可用，用户无感知
```

`_rule_match` 基于预定义规则的纯计算逻辑：

```python
def _rule_match(self, user_profile: UserProfile) -> list[JobRecommendation]:
    """基于规则的回退匹配 —— 无外部依赖，确保可用性"""
    recommendations = []
    for job in self.job_repository.list_active():
        score = self._calculate_rule_score(user_profile, job)
        if score >= self.MIN_THRESHOLD:
            recommendations.append(
                JobRecommendation(
                    code=job.code,
                    match_score=score,
                    reasons=self._extract_rule_reasons(user_profile, job),
                    gaps=self._extract_rule_gaps(user_profile, job),
                    suggested_learning_path=[],  # 规则模式不生成学习路径
                    source="rule",
                    knowledge_references=[],
                )
            )
    return sorted(recommendations, key=lambda r: r.match_score, reverse=True)[:5]
```

### 5. knowledge_references 设计

每个推荐岗位可附带知识库引用，实现结果可溯源：

```python
class KnowledgeReference(BaseModel):
    chunk_id: str           # RagChunk ID，可反查原文
    document_title: str     # 来源文档标题
    content_snippet: str    # 相关片段摘要（前 200 字符）
    relevance_score: float  # 与当前推荐的相关度分数

class JobRecommendation(BaseModel):
    code: str
    match_score: float
    reasons: list[str]
    gaps: list[str]
    suggested_learning_path: list[str]
    source: Literal["llm", "rule"]
    knowledge_references: list[KnowledgeReference] = []
```

引用链路：`JobRecommendation.knowledge_references[] → RagChunk → RagDocument`

---

## 代码导读

### `backend/app/services/job_agent.py`

| 位置 | 内容 | 要点 |
|------|------|------|
| 类定义 | `JobMatchAgent` | 初始化 LLM client、工具集、prompt 模板 |
| `match()` | 主入口方法 | try _llm_match，except 走 _rule_match |
| `_llm_match()` | LLM 匹配 | 构建 AgentExecutor，解析结构化 JSON 输出 |
| `_rule_match()` | 规则回退 | 纯计算逻辑，无外部 API 依赖 |
| `JobMatchTools` | 工具类 | 三个 @tool 装饰的方法，docstring 即工具描述 |

### `backend/app/schemas/job.py`

| 位置 | 内容 | 要点 |
|------|------|------|
| `JobRecommendation` | 推荐结果 schema | 包含 source 字段区分来源 |
| `KnowledgeReference` | 知识引用 schema | 关联 chunk_id 实现溯源 |
| `MatchRequest` | 请求 schema | 用户技能、期望岗位、工作年限等输入 |
| `MatchResponse` | 响应 schema | recommendations 列表 + 元信息（耗时、source） |

---

## 实验步骤

### 实验一：观察 Tool Calling 决策过程

1. 在 `job_agent.py` 中启用 LangChain verbose 模式：`AgentExecutor(verbose=True)`
2. 发送请求："我有 3 年 Python 经验，想找后端岗位"
3. 观察控制台输出的思考链：LLM 选择了哪些工具、传了什么参数
4. 换一个输入："杭州有哪些 P7 的算法岗位"，对比工具选择差异

### 实验二：触发规则回退

1. 临时将 LLM API key 设为无效值（如 `sk-invalid`）
2. 发送匹配请求
3. 检查日志中的异常记录
4. 确认返回结果的 `source` 字段为 `"rule"`
5. 恢复 API key，对比 LLM 结果与规则结果的质量差异

### 实验三：验证知识引用链路

1. 先通过 RAG 服务导入一份岗位技术要求文档
2. 发送匹配请求，确保触发 `query_knowledge` 工具
3. 检查返回的 `knowledge_references` 列表
4. 通过 `chunk_id` 调用 RAG 服务反查原始文档，验证引用准确性

### 实验四：添加自定义工具

1. 在 `JobMatchTools` 中新增 `market_salary` 工具
2. 编写清晰的 docstring 描述工具用途和参数
3. 重启服务，发送 "这个岗位薪资范围是多少" 类型的问题
4. 观察 Agent 是否自动调用新工具

---

## 考核标准

| 等级 | 要求 |
|------|------|
| 及格 | 能说明 Tool Calling 与 if-else 的本质区别，理解三个工具的职责 |
| 良好 | 能独立添加新工具并验证 Agent 正确调用，能解释回退机制的触发条件 |
| 优秀 | 能优化 prompt 提升匹配质量，能设计新的结构化输出 schema 并集成 |

---

## 练习任务

### 任务一：实现匹配结果缓存（难度：中）

设计缓存策略，减少重复 LLM 调用：
- 缓存 key：用户技能集合 hash + 岗位筛选条件 hash
- 缓存有效期：1 小时
- 知识库更新时（RagDocument 新增/变更）主动失效相关缓存
- 使用 Redis 实现，考虑序列化方案

### 任务二：增加置信度评估（难度：中）

在 `_llm_match` 返回结果中增加置信度指标：
- 当推荐列表中 match_score 标准差 > 0.3 时标记为"高区分度"
- 当所有 match_score 都低于 0.5 时标记为"低置信度"
- 低置信度时自动补充 _rule_match 结果作为参考
- 在 MatchResponse 中新增 `confidence_level` 字段

### 任务三：实现多轮对话匹配（难度：高）

扩展 Agent 支持多轮交互式匹配：
- 第一轮：收集用户基本信息（技能、年限、期望城市）
- 第二轮：针对模糊技能追问（如 "Python 经验" → "Web/数据/AI 哪个方向"）
- 第三轮：给出最终推荐并解释理由
- 使用 LangChain ConversationBufferMemory 保持上下文
- 设计对话状态机，跟踪当前处于哪个阶段
