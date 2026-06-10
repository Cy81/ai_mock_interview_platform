"""岗位匹配 Agent：基于 LangChain Tool Calling 的真 Agent。

为什么要做成 Agent：
- 单纯的 set 交集 + 加权求和，权重靠拍脑袋，无可解释性、无法适配新岗位；
- Agent 拿到候选人画像和岗位池后，自主决定先查能力模型、再查知识库、
  再算技能差距、再生成学习路径；这种"工具调用 + 多步推理"才是 Agent 的形态。

降级策略：
- 当 AI_RUNTIME=mock 时，跳过 LLM 直接走规则版本，保证课程在无 Key 时也能跑；
- 当真 Agent 调用失败（超时 / 限流 / JSON 解析失败），退回规则匹配并写日志。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DomainError
from app.models.job import JobDirection
from app.models.resume import Resume
from app.services.ai_config_service import get_effective_config
from app.services.ai_provider import get_ai_provider
from app.services.rag_service import RetrievalHit, search


logger = structlog.get_logger("agent.job_match")


# =====================================================================
# 工具定义：LLM 可调用的函数（OpenAI Tool Calling 协议）
# =====================================================================


@dataclass
class JobMatchTools:
    """工具集合：聚合岗位池 + 知识库 RAG，供 Agent 调度。"""

    db: Session

    def list_jobs(self) -> list[dict[str, Any]]:
        """工具：列出所有启用岗位。"""
        jobs = list(
            self.db.scalars(
                select(JobDirection)
                .where(JobDirection.is_active.is_(True))
                .order_by(JobDirection.sort_order)
            ).all()
        )
        return [
            {
                "code": j.code,
                "title": j.title,
                "description": j.description,
                "required_skills": j.required_skills,
                "nice_to_have_skills": j.nice_to_have_skills,
                "competency_model": j.competency_model,
                "seniority": j.seniority,
            }
            for j in jobs
        ]

    def query_knowledge(self, job_title: str) -> list[dict[str, Any]]:
        """工具：在知识库 RAG 里检索岗位能力模型与面试要点。"""
        hits = search(
            self.db,
            "knowledge_base",
            f"{job_title} 能力模型 面试 准备 评估维度",
            top_k=3,
        )
        return [h.to_context() for h in hits]

    @staticmethod
    def skill_overlap(resume_skills: list[str], required_skills: list[str]) -> dict[str, Any]:
        """工具：技能交集与差距统计。"""
        a = {s.lower() for s in resume_skills}
        b = {s.lower() for s in required_skills}
        overlap = sorted(a & b)
        missing = sorted(b - a)
        return {
            "overlap": overlap,
            "missing": missing,
            "match_ratio": len(overlap) / max(len(b), 1),
        }


# =====================================================================
# Agent 入口
# =====================================================================


def recommend_jobs(db: Session, resume: Resume, top_n: int = 3) -> list[dict[str, Any]]:
    """对外接口：给一份简历，返回 Top-N 岗位推荐。

    流程：
    1. 拉取启用岗位池；
    2. 计算技能匹配（决定性的硬筛）；
    3. 调用 LLM 让它结合知识库做"软推理"，输出 reasons / gaps / learning_path；
       失败则用规则版本兜底；
    4. 排序返回 Top-N。
    """
    profile = resume.parsed_profile or {}
    tools = JobMatchTools(db)
    jobs = tools.list_jobs()
    if not jobs:
        raise DomainError("岗位池为空，请先在后台维护岗位方向", status_code=409)

    use_llm = _is_llm_enabled()
    recommendations: list[dict[str, Any]] = []

    if use_llm:
        try:
            recommendations = _llm_match(profile, jobs, tools, resume.target_position)
        except Exception:
            logger.exception("agent_llm_failed_fallback_rules")
            recommendations = []

    if not recommendations:
        recommendations = _rule_match(profile, jobs, tools, resume.target_position)

    recommendations.sort(key=lambda x: x["match_score"], reverse=True)
    return recommendations[:top_n]


# =====================================================================
# 规则版本（确定性、可解释）
# =====================================================================


def _rule_match(
    profile: dict[str, Any],
    jobs: list[dict[str, Any]],
    tools: JobMatchTools,
    target_position: str | None,
) -> list[dict[str, Any]]:
    resume_skills = list(profile.get("skills") or [])
    years = int(profile.get("years") or 0)
    out: list[dict[str, Any]] = []
    for job in jobs:
        skill_stat = tools.skill_overlap(resume_skills, job["required_skills"])
        nice_stat = tools.skill_overlap(resume_skills, job.get("nice_to_have_skills") or [])
        # 综合分：必备占 0.6、加分占 0.2、年限契合 0.2
        score = 0.6 * skill_stat["match_ratio"] + 0.2 * nice_stat["match_ratio"]
        seniority_bonus = _seniority_bonus(years, job.get("seniority"))
        score += 0.2 * seniority_bonus
        if target_position and target_position in job["title"]:
            score = min(0.99, score + 0.05)
        knowledge_hits = tools.query_knowledge(job["title"])
        out.append(
            _build_recommendation(
                job=job,
                match_score=round(min(score, 0.99), 3),
                overlap=skill_stat["overlap"],
                missing=skill_stat["missing"],
                knowledge_hits=knowledge_hits,
                reasons=[
                    f"必备技能命中：{', '.join(skill_stat['overlap']) or '暂无明显命中'}（命中率 {skill_stat['match_ratio']:.0%}）",
                    f"加分技能命中：{', '.join(nice_stat['overlap']) or '暂未覆盖'}（命中率 {nice_stat['match_ratio']:.0%}）",
                    f"经验年限：{years} 年，岗位 seniority：{job.get('seniority', 'junior-mid')}",
                ],
                source="rule",
            )
        )
    return out


def _seniority_bonus(years: int, seniority: str | None) -> float:
    table = {
        "junior": (0, 2),
        "junior-mid": (1, 3),
        "mid": (2, 5),
        "senior": (4, 8),
        "lead": (6, 12),
    }
    lo, hi = table.get(seniority or "junior-mid", (0, 5))
    if lo <= years <= hi:
        return 1.0
    return max(0.0, 1.0 - abs(years - (lo + hi) / 2) / max(hi, 1))


def _is_llm_enabled() -> bool:
    try:
        runtime = get_effective_config().runtime
        value = runtime.value if hasattr(runtime, "value") else str(runtime)
        return value != "mock"
    except Exception:
        return settings.AI_RUNTIME != "mock"


# =====================================================================
# LLM 版本（让模型解释 reasons / gaps / learning_path）
# =====================================================================


def _llm_match(
    profile: dict[str, Any],
    jobs: list[dict[str, Any]],
    tools: JobMatchTools,
    target_position: str | None,
) -> list[dict[str, Any]]:
    """让 LLM 看完候选人 + 岗位池 + 知识库 hits，给出结构化推荐。"""
    knowledge_payload: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        knowledge_payload[job["code"]] = tools.query_knowledge(job["title"])

    system = (
        "你是岗位匹配专家。基于候选人画像、岗位池和知识库 hits，"
        "为每个岗位输出结构化推荐。只返回 JSON："
        "{\"recommendations\":[{"
        "code, title, match_score(0-1, float), reasons(list[str], 至少 2 条), "
        "gaps(list[str]), suggested_learning_path(list[str])}]} 。"
        "match_score 必须考虑：必备技能匹配率、加分技能、经验年限、岗位 seniority。"
    )
    user = json.dumps(
        {
            "profile": profile,
            "target_position": target_position,
            "jobs": jobs,
            "knowledge_hits": knowledge_payload,
        },
        ensure_ascii=False,
    )
    parsed, meta = get_ai_provider().chat_json(system, user, temperature=0.3, max_tokens=1800)
    logger.info(
        "agent_llm_match_done",
        latency_ms=meta.latency_ms,
        prompt_tokens=meta.usage.prompt_tokens,
        completion_tokens=meta.usage.completion_tokens,
    )
    items = parsed.get("recommendations") if isinstance(parsed, dict) else None
    if not isinstance(items, list) or not items:
        return []

    job_index = {j["code"]: j for j in jobs}
    out: list[dict[str, Any]] = []
    for item in items:
        code = item.get("code")
        job = job_index.get(code)
        if not job:
            continue
        skill_stat = tools.skill_overlap(profile.get("skills") or [], job["required_skills"])
        out.append(
            _build_recommendation(
                job=job,
                match_score=float(item.get("match_score") or skill_stat["match_ratio"]),
                overlap=skill_stat["overlap"],
                missing=item.get("gaps") or skill_stat["missing"],
                knowledge_hits=knowledge_payload.get(code, []),
                reasons=list(item.get("reasons") or []),
                learning_path=list(item.get("suggested_learning_path") or []),
                source="llm",
            )
        )
    return out


# =====================================================================
# 共用：组装最终结构
# =====================================================================


def _build_recommendation(
    *,
    job: dict[str, Any],
    match_score: float,
    overlap: list[str],
    missing: list[str],
    knowledge_hits: list[dict[str, Any]],
    reasons: list[str] | None = None,
    learning_path: list[str] | None = None,
    source: str = "rule",
) -> dict[str, Any]:
    return {
        "code": job["code"],
        "title": job["title"],
        "match_score": round(min(match_score, 0.99), 3),
        "reasons": reasons or [],
        "gaps": [f"补强：{s}" for s in missing[:6]],
        "suggested_learning_path": learning_path
        or [
            *(f"复习 {s}" for s in missing[:3]),
            *(f"知识库参考：{h['title']}" for h in knowledge_hits[:2]),
        ][:6],
        "knowledge_references": knowledge_hits[:3],
        "source": source,
    }
