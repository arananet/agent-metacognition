"""
MetacognitiveEvaluator — isolated Claude call that evaluates agent performance.

Isolation design: the evaluator is a *separate* Claude call that never sees
the agent's own reasoning chain.  This avoids self-serving bias (an agent
that also writes its own evaluation).

Produces a SelfEvaluationReport (AC #2) used to:
  - Determine success for both baseline and meta agents (fair comparison).
  - Supply the instruction_delta for the meta agent (AC #3).

Author: Eduardo Arana
"""
from __future__ import annotations

import json

import anthropic

from .models import AgentRun, SelfEvaluationReport, Task

MODEL = "claude-opus-4-6"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an objective metacognitive evaluator assessing an AI agent's performance.

Your role:
1. Determine whether the agent successfully completed the task.
2. Rate the *quality* of the agent's reasoning process (0-10), independently of \
   whether the final answer is correct.  A wrong answer reached by good reasoning \
   scores higher than a correct answer reached by guessing.
3. Identify specific failure modes (empty list if the response is correct).
4. Propose a concise instruction delta: a short set of imperative directives to \
   prepend to the agent's system prompt for future tasks in the same category, \
   designed to address the observed failure modes or reinforce good patterns.

Be strict, objective, and evidence-based.  Do not award more than 8/10 unless the \
reasoning is genuinely rigorous.  Your output MUST be a single JSON object matching \
the schema you are given — no markdown fences, no preamble, just raw JSON.
"""

_USER_TEMPLATE = """\
## Task
{task_prompt}

## Expected Outcome
{expected_outcome}

## Agent Response
{agent_response}

---
Respond with a JSON object that strictly matches this schema:

{schema}
"""

# ---------------------------------------------------------------------------
# Evaluator class
# ---------------------------------------------------------------------------


class MetacognitiveEvaluator:
    """
    Calls Claude as an isolated judge to evaluate a completed agent run.

    Returns a SelfEvaluationReport that the MetaAgent uses to:
      - Mark the run as success/failure (fair for both agents).
      - Extract the instruction_delta for self-improvement.
    """

    def __init__(self, client: anthropic.Anthropic, model: str = MODEL) -> None:
        self.client = client
        self.model = model
        # Build the JSON schema string once and reuse (helps prompt caching).
        self._schema_str = json.dumps(
            SelfEvaluationReport.model_json_schema(), indent=2
        )

    def evaluate(self, task: Task, run: AgentRun) -> SelfEvaluationReport:
        """
        Evaluate *run* against *task* and return a structured report.

        The evaluation is a completely independent Claude call — the evaluator
        sees only the task description, expected outcome, and agent response.
        It never sees the agent's internal chain-of-thought or system prompt.
        """
        user_content = _USER_TEMPLATE.format(
            task_prompt=task.prompt,
            expected_outcome=task.expected_outcome,
            agent_response=run.response,
            schema=self._schema_str,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )

        raw_text: str = next(
            (b.text for b in response.content if b.type == "text"), "{}"
        )

        return self._parse(raw_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse(self, raw: str) -> SelfEvaluationReport:
        """Parse the JSON response, stripping any accidental markdown fences."""
        text = raw.strip()
        # Strip optional ```json ... ``` wrapper
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first line (``` or ```json) and last line (```)
            text = "\n".join(lines[1:-1]).strip()
        try:
            return SelfEvaluationReport.model_validate_json(text)
        except Exception:
            # Fallback: attempt a lenient parse by extracting the JSON object
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return SelfEvaluationReport.model_validate_json(text[start:end])
            # Last resort: return a neutral report so the run is not lost
            return SelfEvaluationReport(
                task_outcome="Evaluation parsing failed — treating as unknown.",
                success=False,
                reasoning_quality_score=0.0,
                failure_modes=["evaluator_parse_error"],
                instruction_delta="Ensure responses are clear and well-structured.",
            )
