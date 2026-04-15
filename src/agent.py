"""
BaselineAgent — a Claude-powered agent with no metacognitive layer.

Uses streaming + prompt caching on the system prompt.
The injected_delta parameter lets the MetaAgent reuse this class
with an instruction delta prepended, keeping both agents identical
except for that prefix.

Author: Eduardo Arana
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import anthropic

from .models import AgentRun, Task

MODEL = "claude-opus-4-6"

BASE_SYSTEM_PROMPT = """\
You are a precise, methodical problem-solver. \
Your goal is to reason carefully and produce correct, well-explained answers.
"""


class BaselineAgent:
    """
    Baseline agent: single-turn Claude call, no self-reflection.

    Accepts an optional `injected_delta` so the MetaAgent can reuse this
    class while prepending a learned instruction delta (AC #3).
    """

    def __init__(self, client: anthropic.Anthropic, model: str = MODEL) -> None:
        self.client = client
        self.model = model

    def run(self, task: Task, injected_delta: Optional[str] = None) -> AgentRun:
        """Execute the agent on *task*, optionally prepending *injected_delta*."""
        system = self._build_system(injected_delta)
        messages: list[dict] = [{"role": "user", "content": task.prompt}]

        # Stream the response; use get_final_message() for the complete object.
        with self.client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},  # prompt caching
                }
            ],
            messages=messages,
        ) as stream:
            final = stream.get_final_message()

        response_text: str = next(
            (b.text for b in final.content if b.type == "text"), ""
        )

        return AgentRun(
            task_id=task.id,
            response=response_text,
            success=False,           # set by the evaluator after this call
            messages=messages + [{"role": "assistant", "content": response_text}],
            model=self.model,
            timestamp=datetime.utcnow(),
            injected_delta=injected_delta,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system(self, injected_delta: Optional[str]) -> str:
        if injected_delta:
            return f"{injected_delta}\n\n{BASE_SYSTEM_PROMPT}"
        return BASE_SYSTEM_PROMPT
