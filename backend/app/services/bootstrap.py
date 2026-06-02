"""默认数据初始化：岗位池 + 双 RAG 种子 + 默认管理员。

注意：仅在 dev/test 环境调用。生产应通过 Alembic seed 或后台 CRUD 维护。
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.job import JobDirection
from app.models.rag import RagDocument, RagType
from app.models.user import User, UserRole
from app.services.rag_service import upsert_document


logger = structlog.get_logger("bootstrap")


DEFAULT_JOBS = [
    {
        "code": "python_backend",
        "title": "Python 后端工程师",
        "description": "负责 FastAPI 服务、数据库建模、异步任务和生产部署。",
        "required_skills": ["Python", "FastAPI", "SQLAlchemy", "PostgreSQL", "Redis", "Docker"],
        "nice_to_have_skills": ["Linux", "Kubernetes", "Kafka"],
        "competency_model": {"api": 0.25, "database": 0.25, "reliability": 0.25, "testing": 0.25},
        "seniority": "mid",
        "salary_range": "20-40K",
        "sort_order": 1,
    },
    {
        "code": "ai_app_engineer",
        "title": "AI 应用工程师",
        "description": "负责 LLM 应用、Prompt、工具调用、RAG 与业务系统集成。",
        "required_skills": ["Python", "RAG", "LangChain", "FastAPI", "Redis", "Docker"],
        "nice_to_have_skills": ["DeepSeek", "Embedding", "Agent"],
        "competency_model": {"llm": 0.35, "rag": 0.3, "backend": 0.2, "product": 0.15},
        "seniority": "mid",
        "salary_range": "25-50K",
        "sort_order": 2,
    },
    {
        "code": "rag_engineer",
        "title": "RAG 工程师",
        "description": "负责知识库切分、向量化、检索、评估和召回质量优化。",
        "required_skills": ["Python", "RAG", "pgvector", "LangChain", "PostgreSQL", "DashScope"],
        "nice_to_have_skills": ["Reranker", "Elasticsearch", "Hybrid Search"],
        "competency_model": {"retrieval": 0.35, "embedding": 0.25, "evaluation": 0.25, "backend": 0.15},
        "seniority": "mid",
        "salary_range": "25-50K",
        "sort_order": 3,
    },
    {
        "code": "data_analyst",
        "title": "数据分析工程师",
        "description": "负责指标体系、SQL 分析、Python 数据处理和可视化汇报。",
        "required_skills": ["Python", "SQL", "Pandas", "数据分析"],
        "nice_to_have_skills": ["可视化", "ClickHouse", "BI"],
        "competency_model": {"sql": 0.3, "analysis": 0.35, "python": 0.2, "communication": 0.15},
        "seniority": "junior-mid",
        "salary_range": "15-30K",
        "sort_order": 4,
    },
    {
        "code": "test_development",
        "title": "测试开发工程师",
        "description": "负责自动化测试、接口测试、质量平台和持续集成。",
        "required_skills": ["Python", "pytest", "FastAPI", "Docker", "CI"],
        "nice_to_have_skills": ["Selenium", "Locust", "Allure"],
        "competency_model": {"automation": 0.35, "backend": 0.25, "quality": 0.25, "devops": 0.15},
        "seniority": "junior-mid",
        "salary_range": "15-30K",
        "sort_order": 5,
    },
]


QUESTION_BANK_DOC = """[Python 后端] 请解释 FastAPI 的依赖注入如何用于数据库 Session 与权限校验，结合代码说明。
[Python 后端] SQLAlchemy 2.x 中 Session 生命周期如何设计，如何避免连接泄漏。
[Python 后端] FastAPI 项目里如何编写一个生产可用的统一错误处理与请求 ID 中间件。
[AI 应用] RAG 系统从文档入库到生成回答有哪些关键环节，如何评估召回质量。
[AI 应用] DeepSeek 这类 OpenAI Compatible API 接入时，如何做超时、重试、降级和成本控制。
[AI 应用] 描述一次你写过的 Agent，它解决了什么问题、用了哪些工具、如何评估效果。
[RAG] pgvector 中向量维度如何与 Embedding 模型保持一致，如何用 HNSW 索引提速。
[RAG] RecursiveCharacterTextSplitter 的 chunk size 和 overlap 如何影响召回与成本。
[RAG] 在中文场景下，召回准确率不高时你会从哪些维度排查（chunk / embedding / 检索 / rerank）？
[数据分析] 请描述一次从业务问题到指标口径、SQL 查询、结论交付的完整流程。
[数据分析] 一次你做过的指标拆解或归因分析，如何衡量结论的可信度。
[测试开发] 如何为 FastAPI + Celery 项目设计单元测试和集成测试边界。
[测试开发] 接口自动化怎么做数据隔离与并发幂等，如何与 CI 集成。
"""


KNOWLEDGE_BASE_DOC = """岗位能力模型：
Python 后端工程师需要掌握 API 设计、ORM、事务、缓存、异步任务、测试和部署。
AI 应用工程师需要掌握 Prompt、结构化输出、工具调用、RAG、模型降级和业务指标。
RAG 工程师需要掌握文档清洗、切分策略、Embedding、向量库、混合检索、重排和评估集。
数据分析工程师需要掌握 SQL、统计思维、Python 数据处理、指标体系和清晰表达。
测试开发工程师需要掌握 pytest、接口自动化、Mock、测试数据管理、CI 和质量度量。

面试评分维度建议：
1. 技术准确性：是否能准确解释概念，是否使用了错误的术语；
2. 项目表达：是否使用 STAR 结构，是否有量化结果与失败复盘；
3. 工程化意识：是否覆盖测试、监控、超时重试、灰度发布等生产维度；
4. 岗位匹配：是否能把回答收敛到目标岗位关心的能力点。

回答改进建议模板：
- STAR：背景-任务-行动-结果，再补一段"反思"；
- 量化：响应时间、吞吐、成功率、召回率、成本下降；
- 取舍：为什么不用方案 B，B 的代价是什么；
- 失败：上线后的真实问题与你做的工程改造。
"""


def bootstrap_data(db: Session) -> None:
    _bootstrap_admin(db)
    _bootstrap_jobs(db)
    _bootstrap_rag(db)


def _bootstrap_admin(db: Session) -> None:
    if db.scalar(select(User).where(User.role == UserRole.SUPERADMIN)):
        return
    admin = User(
        email=settings.DEFAULT_ADMIN_EMAIL,
        full_name=settings.DEFAULT_ADMIN_NAME,
        hashed_password=get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
        role=UserRole.SUPERADMIN,
        is_active=True,
        is_email_verified=True,
    )
    db.add(admin)
    db.commit()
    logger.info("admin_seeded", email=settings.DEFAULT_ADMIN_EMAIL)


def _bootstrap_jobs(db: Session) -> None:
    if db.scalar(select(JobDirection).limit(1)):
        return
    db.add_all(JobDirection(**item) for item in DEFAULT_JOBS)
    db.commit()
    logger.info("jobs_seeded", count=len(DEFAULT_JOBS))


def _bootstrap_rag(db: Session) -> None:
    if db.scalar(select(RagDocument).limit(1)):
        return
    upsert_document(
        db,
        rag_type=RagType.QUESTION_BANK,
        title="内置面试题库",
        content=QUESTION_BANK_DOC,
        metadata={"source": "seed", "language": "zh"},
    )
    upsert_document(
        db,
        rag_type=RagType.KNOWLEDGE_BASE,
        title="岗位能力知识库",
        content=KNOWLEDGE_BASE_DOC,
        metadata={"source": "seed", "language": "zh"},
    )
    logger.info("rag_seeded")
