# LangChain + SSE 面试链路设计

日期：2026-06-03

## 背景

当前项目已经具备简历上传解析、岗位方向、面试创建、答题、完成评分、JWT 认证、后台管理基础能力，并且后端已有一个演示性质的 SSE 端点 `GET /api/v1/interviews/{interview_id}/answer/stream`。用户希望参考线上系统亮点，优先强化 AI 模拟面试体验，并明确要求 Agent 使用 LangChain 框架。

本设计聚焦第一阶段：把面试核心链路升级为 LangChain 编排，并提供可被前端消费的结构化 SSE 事件。目标是让现有系统更接近“多轮 AI 面试、逐字输出、实时评分、综合报告”的产品体验，同时尽量保持现有 API、数据库和前端页面可兼容。

## 目标

1. 使用 LangChain 作为面试 Agent 编排框架。
2. 支持基于简历、岗位能力模型、题库 RAG 的结构化出题。
3. 支持用户答题后的流式追问、点评或下一步引导。
4. 支持完成面试后的结构化评分和综合报告生成。
5. 用 SSE 推送清晰的事件流，前端可以展示“AI 正在生成、逐字输出、评分完成、报告就绪”等状态。
6. 保留 mock 运行模式，测试和本地开发不依赖真实模型 API。

## 非目标

1. 第一阶段不重做后台管理系统，只保证后台能继续查看现有面试记录和报告字段。
2. 第一阶段不做完整工作流事件日志表，不提供断点续流。
3. 第一阶段不大改数据库模型；若必须新增字段，只限小范围兼容字段，并优先使用现有字段。
4. 第一阶段不重构简历解析链路，只把已解析的 `parsed_profile` 作为 Agent 输入。

## 推荐方案

采用“LangChain 服务层 + 现有业务服务兼容”的方案。

后端新增独立的 `interview_agents` 服务层。该层用 LangChain prompt、runnable、tool 和结构化输出解析来承接 Agent 行为；现有 `interview_service` 继续负责数据库状态机、权限校验、题目和报告落库。模型连接继续复用 DeepSeek 的 OpenAI-compatible 配置，但通过 `langchain-openai` 创建 LangChain ChatModel。

该方案比只包装现有 `AIProvider` 更能满足 LangChain Agent 要求；比完整工作流重建风险低，适合当前实战项目快速升级。

## 架构

新增后端模块：

- `backend/app/services/interview_agents/models.py`：定义 Agent 输入、输出、SSE 事件等 Pydantic 模型。
- `backend/app/services/interview_agents/llm.py`：创建 LangChain ChatModel，支持 DeepSeek 和 mock。
- `backend/app/services/interview_agents/planner.py`：`InterviewPlannerAgent`，根据简历、岗位和目标类型规划难度、技能覆盖和题型比例。
- `backend/app/services/interview_agents/question_generator.py`：`QuestionGenerationAgent`，生成结构化面试题。
- `backend/app/services/interview_agents/followup.py`：`FollowupAgent`，根据当前题目和回答生成追问、点评或下一题引导。
- `backend/app/services/interview_agents/scoring.py`：`ScoringAgent`，生成逐题评分和维度评分。
- `backend/app/services/interview_agents/report.py`：`ReportAgent`，整理最终综合报告。
- `backend/app/services/interview_agents/events.py`：SSE 事件格式化和流式编排。

现有模块改造：

- `interview_service.create_interview`：内部改用 `QuestionGenerationAgent` 生成题目，保留原函数签名和返回结构。
- `interview_service.finish_interview`：内部改用 `ScoringAgent` 和 `ReportAgent`，保留 `score_report`、`overall_score` 和每题分数字段写回。
- `api/v1/interviews.py`：新增结构化 SSE 端点，保留旧演示端点以避免兼容问题。
- `frontend/src/views/MockInterview.vue`：新增 EventSource 或 fetch stream 消费逻辑，展示流式追问、状态和评分进度。

## Agent 设计

### InterviewPlannerAgent

输入：岗位标题、岗位能力模型、简历画像、目标类型、题目数量。

输出：面试计划，包括难度、核心技能、题型比例、面试风格和注意事项。目标类型优先从请求或岗位元数据读取；没有明确值时按简历年限推断，0-1 年偏实习或初级，2 年以上偏正式。

### QuestionGenerationAgent

输入：面试计划、简历画像、岗位能力模型、题库 RAG 片段。

输出：题目列表，每题包含 `position`、`type`、`difficulty`、`skill`、`question`、`rubric`、`reference_chunk_ids`。输出结构必须兼容现有 `InterviewQuestion`。

### FollowupAgent

输入：面试详情、当前题目、用户回答、历史问答。

输出：流式文本和最终结构化结果。结果包括 `action`，可选值为 `followup`、`comment`、`next_question_hint`；还包括 `content`、`confidence`、`suggested_next_position`。SSE 中 token 级输出用于前端打字机效果。

### ScoringAgent

输入：全部题目、答案、rubric、岗位能力模型、知识库 RAG 片段。

输出：逐题分数、评语、维度分数和总分。逐题分数写回 `InterviewAnswer.score/comment`，总分写回 `Interview.overall_score`。

### ReportAgent

输入：评分结果、简历画像、岗位信息。

输出：综合报告，包含优势、短板、岗位匹配度、学习计划和下一次练习建议。报告写入 `Interview.score_report`。

## SSE 事件协议

新增端点：

`GET /api/v1/interviews/{interview_id}/stream`

查询参数：

- `mode=followup|scoring`，默认 `followup`。
- `question_id`，`followup` 模式必填。

每条事件使用 JSON：

```text
event: followup_delta
data: {"content":"...","interview_id":1,"question_id":2}
```

事件类型：

- `planning_started`
- `planning_done`
- `question_generation_started`
- `question_generation_done`
- `followup_started`
- `followup_delta`
- `followup_done`
- `scoring_started`
- `scoring_done`
- `report_ready`
- `error`
- `done`

第一阶段重点实现 `followup_*`、`scoring_*`、`report_ready` 和 `error`。创建面试时的 `planning_*`、`question_generation_*` 可以先在后端内部使用，后续如需前端展示创建过程再开放。

## 数据流

### 创建面试

1. 校验当前用户、简历和岗位。
2. 读取简历 `parsed_profile` 和岗位 `competency_model`。
3. 查询题库 RAG 片段。
4. `InterviewPlannerAgent` 生成面试计划。
5. `QuestionGenerationAgent` 生成题目。
6. 题目写入现有 `InterviewQuestion`，面试状态进入 `IN_PROGRESS`。

### 答题后追问

1. 用户提交答案到现有 `POST /api/v1/interviews/{id}/answers`。
2. 前端打开 `GET /api/v1/interviews/{id}/stream?mode=followup&question_id=...`。
3. `FollowupAgent` 按 token 推送 `followup_delta`。
4. 完整结果通过 `followup_done` 推送。
5. 当前阶段不强制把追问持久化为新题，避免破坏现有题目模型；后续可增加追问记录表。

### 完成评分

1. 用户调用现有 `POST /api/v1/interviews/{id}/finish` 或前端使用 scoring SSE。
2. 服务进入 `SCORING` 状态。
3. `ScoringAgent` 生成结构化评分。
4. `ReportAgent` 生成综合报告。
5. 分数和报告写回现有字段，状态进入 `COMPLETED`。
6. 如果使用 SSE，则按 `scoring_started`、`scoring_done`、`report_ready`、`done` 推送。

## 错误处理

1. LangChain 调用异常时，记录 `interview_id`、用户 ID、模型、阶段和耗时。
2. JSON 解析失败时，尝试一次结构修复；仍失败则返回明确 `error` 事件，并把同步接口异常透出为业务错误。
3. 创建面试失败时沿用现有逻辑，状态设为 `FAILED`。
4. 评分失败时回滚到 `IN_PROGRESS`，用户可以再次触发完成。
5. SSE 流中出现错误时，先推送 `error`，再推送 `done` 并关闭连接。

## 前端体验

`MockInterview.vue` 保留现有题目和答题流程，新增 AI 面试官反馈区域：

- 提交答案后显示生成状态。
- `followup_delta` 到达时逐字追加内容。
- `followup_done` 后展示完整追问或点评。
- 完成面试时展示评分进度；报告就绪后跳转或提示查看报告。

前端需要处理连接关闭、错误事件、重复点击和刷新页面。第一阶段不做复杂视觉重构，只把流式交互完整接入。

## 测试

后端测试：

- mock LangChain runtime 下，创建面试能生成结构化题目。
- `FollowupAgent` 输出可以被 SSE 格式化为合法事件。
- scoring 模式会写回 `overall_score`、`score_report` 和每题分数。
- 旧的创建、答题、完成接口保持兼容。
- 真实 API key 不存在时，mock 测试仍可通过。

前端测试：

- MockInterview 页面能消费 `followup_delta` 并追加文本。
- `error` 事件能展示失败状态。
- 完成评分后能进入报告查看路径。

验证命令：

- `python -m pytest`
- `npm run build`

## 风险和取舍

1. EventSource 只能 GET，且自定义 Header 支持有限；如果当前前端 JWT 依赖 Authorization Header，SSE 端点可能需要短期 token 查询参数或改用 `fetch + ReadableStream`。设计上优先支持 `fetch + ReadableStream`，若现有认证能用 cookie 再用 EventSource。
2. 第一阶段不持久化追问内容，因此刷新后可能看不到刚才的 AI 点评。若产品需要历史追问，需要后续增加追问表。
3. LangChain 版本已固定在 `0.3.x`，实现时应使用该版本稳定 API，避免引入新版写法导致依赖冲突。
4. Mock 与真实模型输出可能有差异，结构化输出解析和测试必须覆盖降级路径。

## 验收标准

1. 后端在 mock 模式下可以完成创建面试、提交答案、流式追问、完成评分和报告生成。
2. Agent 相关实现明确使用 LangChain，而不是只调用原始 OpenAI SDK。
3. SSE 输出为稳定 JSON 事件，前端可以区分 delta、完成、错误和报告就绪状态。
4. 现有接口兼容，不破坏用户注册登录、简历上传、岗位管理、后台查看面试记录。
5. 自动化测试覆盖核心 Agent 输出和 SSE 事件顺序。
