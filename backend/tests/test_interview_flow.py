"""主流程端到端：注册 -> 简历 -> 推荐 -> 出题 -> 答题 -> 评分 -> 取消 -> 错误码。"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_full_business_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    # 1) 录入文本简历
    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "resume.txt",
            "target_position": "AI 应用工程师",
            "text": "姓名：李雷\n3年 Python FastAPI PostgreSQL Redis Celery RAG LangChain Docker 项目经验。",
        },
    )
    assert resume_response.status_code == 201, resume_response.text
    resume = resume_response.json()
    assert "RAG" in resume["parsed_profile"]["skills"]
    assert resume["parse_status"] == "parsed"

    # 2) 推荐岗位
    recommend_response = client.post(
        "/api/v1/jobs/recommend",
        headers=auth_headers,
        json={"resume_id": resume["id"], "top_n": 3},
    )
    assert recommend_response.status_code == 200, recommend_response.text
    recommendations = recommend_response.json()["recommendations"]
    assert recommendations
    top_job = recommendations[0]
    assert top_job["match_score"] > 0

    # 3) 创建面试 + 幂等键
    payload = {
        "resume_id": resume["id"],
        "job_code": top_job["code"],
        "question_count": 3,
        "idempotency_key": "test-key-001",
    }
    interview_response = client.post("/api/v1/interviews", headers=auth_headers, json=payload)
    assert interview_response.status_code == 201
    interview = interview_response.json()
    assert len(interview["questions"]) == 3
    assert all(q["rubric"] for q in interview["questions"])
    assert all(q["difficulty"] in {"basic", "intermediate", "advanced"} for q in interview["questions"])
    assert interview["status"] == "in_progress"

    # 重复请求应返回相同面试
    again = client.post("/api/v1/interviews", headers=auth_headers, json=payload)
    assert again.status_code == 201
    assert again.json()["id"] == interview["id"]

    # 4) 答题（模拟答案足够长）
    for question in interview["questions"]:
        answer_response = client.post(
            f"/api/v1/interviews/{interview['id']}/answers",
            headers=auth_headers,
            json={
                "question_id": question["id"],
                "answer": (
                    "我的方案会先定义目标和边界，再设计接口、测试、监控、降级和安全策略，"
                    "并结合项目指标复盘性能、稳定性与成本优化。"
                ),
                "duration_ms": 30000,
            },
        )
        assert answer_response.status_code == 200

    # 5) 完成面试
    finish_response = client.post(
        f"/api/v1/interviews/{interview['id']}/finish", headers=auth_headers
    )
    assert finish_response.status_code == 200, finish_response.text
    finished = finish_response.json()
    assert finished["status"] == "completed"
    assert finished["overall_score"] is not None
    report = finished["score_report"]
    assert report["overall_score"] > 0
    assert "dimension_scores" in report

    # 6) 报告接口
    report_resp = client.get(f"/api/v1/reports/{interview['id']}", headers=auth_headers)
    assert report_resp.status_code == 200
    assert report_resp.json()["status"] == "completed"


def test_conversational_interview_turn_generates_next_question(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "conversation-resume.txt",
            "target_position": "AI 应用工程师",
            "text": (
                "姓名：李雷\n3年 Python FastAPI RAG LangChain SSE Docker 项目经验。"
                "负责 AI 模拟面试平台：简历解析、RAG 题库召回、流式追问和评分报告。"
            ),
        },
    )
    assert resume_response.status_code == 201, resume_response.text
    resume = resume_response.json()

    recommend_response = client.post(
        "/api/v1/jobs/recommend",
        headers=auth_headers,
        json={"resume_id": resume["id"], "top_n": 1},
    )
    assert recommend_response.status_code == 200, recommend_response.text
    job = recommend_response.json()["recommendations"][0]

    interview_response = client.post(
        "/api/v1/interviews",
        headers=auth_headers,
        json={
            "resume_id": resume["id"],
            "job_code": job["code"],
            "question_count": 4,
            "conversational": True,
            "idempotency_key": "conversation-turn-key",
        },
    )
    assert interview_response.status_code == 201, interview_response.text
    interview = interview_response.json()
    assert interview["question_count"] == 4
    assert len(interview["questions"]) == 1

    first_question = interview["questions"][0]
    turn_response = client.post(
        f"/api/v1/interviews/{interview['id']}/turns",
        headers=auth_headers,
        json={
            "question_id": first_question["id"],
            "answer": (
                "我会用 LangChain 编排面试 Agent，用 RAG 召回题库和简历证据，"
                "再通过 SSE 把追问过程流式返回给前端。"
            ),
            "duration_ms": 25000,
        },
    )

    assert turn_response.status_code == 200, turn_response.text
    payload = turn_response.json()
    assert payload["answered_question_id"] == first_question["id"]
    assert payload["completed"] is False
    assert payload["next_question"]["position"] == 2
    assert "刚才" in payload["next_question"]["question"]
    assert any(
        token in payload["next_question"]["question"]
        for token in ("RAG", "LangChain", "FastAPI")
    )
    assert len(payload["interview"]["questions"]) == 2


def test_create_interview_falls_back_when_ai_generation_fails(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    import app.services.interview_service as interview_service

    class FailingRuntime:
        def generate_interview_questions(self, **kwargs):
            raise RuntimeError("upstream model returned invalid payload")

    monkeypatch.setattr(
        interview_service,
        "get_interview_agent_runtime",
        lambda: FailingRuntime(),
    )

    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "fallback-resume.txt",
            "target_position": "AI 应用工程师",
            "text": "姓名：李雷\n3年 Python FastAPI RAG LangChain Docker 项目经验。",
        },
    )
    assert resume_response.status_code == 201, resume_response.text
    resume = resume_response.json()

    recommend_response = client.post(
        "/api/v1/jobs/recommend",
        headers=auth_headers,
        json={"resume_id": resume["id"], "top_n": 1},
    )
    assert recommend_response.status_code == 200, recommend_response.text
    job = recommend_response.json()["recommendations"][0]

    interview_response = client.post(
        "/api/v1/interviews",
        headers=auth_headers,
        json={
            "resume_id": resume["id"],
            "job_code": job["code"],
            "question_count": 2,
            "idempotency_key": "fallback-question-generation",
        },
    )

    assert interview_response.status_code == 201, interview_response.text
    interview = interview_response.json()
    assert interview["status"] == "in_progress"
    assert len(interview["questions"]) == 2
    assert all(question["rubric"] for question in interview["questions"])


def test_interview_turn_falls_back_when_next_question_generation_fails(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "fallback-turn-resume.txt",
            "target_position": "AI 应用工程师",
            "text": "姓名：李雷\n3年 Python FastAPI RAG LangChain Docker 项目经验。",
        },
    )
    assert resume_response.status_code == 201, resume_response.text
    resume = resume_response.json()

    recommend_response = client.post(
        "/api/v1/jobs/recommend",
        headers=auth_headers,
        json={"resume_id": resume["id"], "top_n": 1},
    )
    assert recommend_response.status_code == 200, recommend_response.text
    job = recommend_response.json()["recommendations"][0]

    interview_response = client.post(
        "/api/v1/interviews",
        headers=auth_headers,
        json={
            "resume_id": resume["id"],
            "job_code": job["code"],
            "question_count": 3,
            "conversational": True,
            "idempotency_key": "fallback-next-question",
        },
    )
    assert interview_response.status_code == 201, interview_response.text
    interview = interview_response.json()
    first_question = interview["questions"][0]

    import app.services.interview_service as interview_service

    class FailingRuntime:
        def generate_next_question(self, **kwargs):
            raise RuntimeError("next question failed")

    monkeypatch.setattr(
        interview_service,
        "get_interview_agent_runtime",
        lambda: FailingRuntime(),
    )

    turn_response = client.post(
        f"/api/v1/interviews/{interview['id']}/turns",
        headers=auth_headers,
        json={
            "question_id": first_question["id"],
            "answer": "我会结合 RAG 召回、LangChain 编排和 SSE 流式输出设计完整链路。",
            "duration_ms": 20000,
        },
    )

    assert turn_response.status_code == 200, turn_response.text
    payload = turn_response.json()
    assert payload["completed"] is False
    assert payload["next_question"]["position"] == 2
    assert "刚才" in payload["next_question"]["question"]


def test_finish_interview_falls_back_when_ai_scoring_fails(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "fallback-score-resume.txt",
            "target_position": "AI 应用工程师",
            "text": "姓名：李雷\n3年 Python FastAPI RAG LangChain Docker 项目经验。",
        },
    )
    assert resume_response.status_code == 201, resume_response.text
    resume = resume_response.json()

    recommend_response = client.post(
        "/api/v1/jobs/recommend",
        headers=auth_headers,
        json={"resume_id": resume["id"], "top_n": 1},
    )
    assert recommend_response.status_code == 200, recommend_response.text
    job = recommend_response.json()["recommendations"][0]

    interview_response = client.post(
        "/api/v1/interviews",
        headers=auth_headers,
        json={
            "resume_id": resume["id"],
            "job_code": job["code"],
            "question_count": 2,
            "idempotency_key": "fallback-scoring",
        },
    )
    assert interview_response.status_code == 201, interview_response.text
    interview = interview_response.json()

    for question in interview["questions"]:
        answer_response = client.post(
            f"/api/v1/interviews/{interview['id']}/answers",
            headers=auth_headers,
            json={
                "question_id": question["id"],
                "answer": (
                    "我会先拆解业务目标，再用 FastAPI 设计接口，用 LangChain 编排模型调用，"
                    "结合 RAG 召回简历证据，并用监控指标验证效果。"
                ),
                "duration_ms": 30000,
            },
        )
        assert answer_response.status_code == 200, answer_response.text

    import app.services.interview_service as interview_service

    class FailingRuntime:
        def score_interview(self, **kwargs):
            raise RuntimeError("scoring failed")

    monkeypatch.setattr(
        interview_service,
        "get_interview_agent_runtime",
        lambda: FailingRuntime(),
    )

    finish_response = client.post(
        f"/api/v1/interviews/{interview['id']}/finish",
        headers=auth_headers,
    )

    assert finish_response.status_code == 200, finish_response.text
    finished = finish_response.json()
    assert finished["status"] == "completed"
    assert finished["overall_score"] > 0
    assert finished["score_report"]["source"] == "local-fallback"
    assert len(finished["score_report"]["question_scores"]) == len(interview["questions"])
    assert all(answer["score"] is not None for answer in finished["answers"])


def test_rag_search(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/rag/search",
        headers=auth_headers,
        json={"rag_type": "question_bank", "query": "FastAPI 依赖注入 测试", "top_k": 3},
    )
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits, "至少应该召回种子题库"
    assert hits[0]["score"] > 0


def test_admin_create_rag_requires_admin(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # 普通用户不能写入 RAG
    response = client.post(
        "/api/v1/admin/rag/documents",
        headers=auth_headers,
        json={
            "rag_type": "knowledge_base",
            "title": "禁止写入",
            "content": "普通用户不应该能写入",
            "metadata": {},
        },
    )
    assert response.status_code == 403


def test_error_semantics(client: TestClient, auth_headers: dict[str, str]) -> None:
    # 未带 token
    assert client.get("/api/v1/resumes").status_code == 401

    # 简历过短
    short = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={"filename": "short.txt", "text": "太短"},
    )
    assert short.status_code == 422

    # 不存在的报告
    missing = client.get("/api/v1/reports/9999", headers=auth_headers)
    assert missing.status_code == 404
