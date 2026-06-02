from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class FollowupAgent:
    def stream(self, **_: Any) -> Iterator[str]:
        feedback = "回答覆盖了核心思路，可以继续补充项目细节、工程权衡和验证方式。"
        for index in range(0, len(feedback), 8):
            yield feedback[index:index + 8]
