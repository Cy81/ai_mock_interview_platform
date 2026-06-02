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
