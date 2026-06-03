from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _create_interview_with_answers(client: TestClient, auth_headers: dict[str, str]) -> dict:
    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "stream-resume.txt",
            "target_position": "AI 应用工程师",
            "text": "姓名：李雷\n3年 Python FastAPI PostgreSQL Redis Celery RAG LangChain Docker 项目经验。",
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
            "idempotency_key": "stream-test-key",
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
                    "我会先定义目标和边界，再设计接口、测试、监控、降级和安全策略，"
                    "并根据指标复盘迭代。"
                ),
                "duration_ms": 18000,
            },
        )
        assert answer_response.status_code == 200, answer_response.text

    return interview


def _read_sse_events(response) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    current_event: str | None = None
    current_data: str | None = None

    for line in response.iter_lines():
        if not line:
            if current_event and current_data is not None:
                events.append(
                    {
                        "event": current_event,
                        "data": json.loads(current_data),
                    }
                )
            current_event = None
            current_data = None
            continue

        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
        if decoded.startswith("event: "):
            current_event = decoded.removeprefix("event: ")
        elif decoded.startswith("data: "):
            current_data = decoded.removeprefix("data: ")

    return events


def test_followup_stream_emits_structured_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    interview = _create_interview_with_answers(client, auth_headers)
    question_id = interview["questions"][0]["id"]

    with client.stream(
        "GET",
        f"/api/v1/interviews/{interview['id']}/stream",
        headers=auth_headers,
        params={"mode": "followup", "question_id": question_id},
    ) as response:
        assert response.status_code == 200, response.text
        events = _read_sse_events(response)

    names = [event["event"] for event in events]
    assert names[0] == "followup_started"
    assert "followup_delta" in names[1:-2]
    assert names[-2:] == ["followup_done", "done"]
    assert events[0]["data"]["interview_id"] == interview["id"]
    assert events[0]["data"]["question_id"] == question_id
    assert events[1]["data"]["content"]
    assert events[-2]["data"]["content"]


def test_scoring_stream_emits_structured_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    interview = _create_interview_with_answers(client, auth_headers)

    with client.stream(
        "GET",
        f"/api/v1/interviews/{interview['id']}/stream",
        headers=auth_headers,
        params={"mode": "scoring"},
    ) as response:
        assert response.status_code == 200, response.text
        events = _read_sse_events(response)

    assert [event["event"] for event in events[:4]] == [
        "scoring_started",
        "scoring_done",
        "report_ready",
        "done",
    ]
    assert events[0]["data"]["interview_id"] == interview["id"]
    assert events[1]["data"]["interview_id"] == interview["id"]
    assert events[2]["data"]["report"]["overall_score"] > 0
    assert events[2]["data"]["report"]["question_scores"]
