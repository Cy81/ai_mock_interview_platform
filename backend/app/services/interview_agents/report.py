from __future__ import annotations

from app.services.interview_agents.models import ReportResult, ScoreResult


class ReportAgent:
    def build_report(self, score: ScoreResult) -> dict[str, object]:
        next_practice = score.learning_plan or ["继续练习项目复盘和技术取舍表达"]
        return ReportResult(
            **score.model_dump(mode="json"),
            next_practice=next_practice,
        ).model_dump(mode="json")
