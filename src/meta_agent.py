"""
MetaAgent — the self-evolving, metacognitive agent.

Wraps BaselineAgent with a full metacognitive loop:
  Observe → Evaluate → Reflect → Update

Maintains a per-category instruction delta store.  Before each task run the
relevant delta (if any) is prepended to the system prompt (AC #3).  After the
run, the evaluator produces a new delta that replaces the stored one for that
category, ready for the next task.

Every cycle is recorded via CycleLogger (AC #4).

Author: Eduardo Arana
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import anthropic

from .agent import BaselineAgent
from .evaluator import MetacognitiveEvaluator
from .logger import CycleLogger
from .models import AgentRun, MetacognitiveLog, Task


class MetaAgent:
    """
    Self-improving agent that accumulates instruction deltas per task category.

    The delta store is in-memory and keyed by category (str).  Each task run
    may update the stored delta for its category, influencing all subsequent
    runs in that same category (AC #3).
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        logger: CycleLogger,
        model: str = "claude-opus-4-6",
    ) -> None:
        self._agent = BaselineAgent(client, model)
        self._evaluator = MetacognitiveEvaluator(client, model)
        self._logger = logger
        # Instruction delta store: category → current delta string
        self._deltas: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, task: Task) -> AgentRun:
        """
        Run the metacognitive loop for *task*.

        Steps:
          1. Observe  — retrieve current delta for task.category; run the agent.
          2. Evaluate — call the isolated evaluator on the completed run.
          3. Reflect  — decide whether the delta changed.
          4. Update   — store the new delta; log the full cycle.

        Returns the AgentRun with `success` populated by the evaluator.
        """
        # ── 1. Observe ────────────────────────────────────────────────
        current_delta: Optional[str] = self._deltas.get(task.category)
        agent_run = self._agent.run(task, injected_delta=current_delta)

        # ── 2. Evaluate ───────────────────────────────────────────────
        report = self._evaluator.evaluate(task, agent_run)
        agent_run.success = report.success

        # ── 3. Reflect ────────────────────────────────────────────────
        new_delta = report.instruction_delta
        delta_changed = new_delta != current_delta

        # ── 4. Update ─────────────────────────────────────────────────
        self._deltas[task.category] = new_delta

        cycle_log = MetacognitiveLog(
            cycle_id=str(uuid.uuid4()),
            task_id=task.id,
            task_category=task.category,
            timestamp=datetime.utcnow(),
            agent_response_preview=agent_run.response[:300],
            agent_success=agent_run.success,
            injected_delta=current_delta,
            report=report,
            previous_delta=current_delta,
            delta_changed=delta_changed,
            new_delta=new_delta,
        )
        self._logger.log(cycle_log)

        return agent_run

    def current_delta(self, category: str) -> Optional[str]:
        """Return the current instruction delta for *category* (for reporting)."""
        return self._deltas.get(category)
