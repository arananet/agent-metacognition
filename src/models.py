"""
Data models for the Agent Meta Cognition POC.

Author: Eduardo Arana
Project: agent-metacognition
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Task — benchmark definition (loaded from YAML)
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    category: str
    title: str
    prompt: str
    expected_outcome: str
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AgentRun — result of one agent invocation on one task
# ---------------------------------------------------------------------------

@dataclass
class AgentRun:
    task_id: str
    response: str
    success: bool
    messages: list[dict]          # full conversation history
    model: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    injected_delta: Optional[str] = None  # instruction delta prepended to system


# ---------------------------------------------------------------------------
# SelfEvaluationReport — structured output of the metacognitive evaluator
# ---------------------------------------------------------------------------

class SelfEvaluationReport(BaseModel):
    """
    Structured self-evaluation produced by the metacognitive layer after
    each agent run.  All four required fields map directly to AC #2.
    """
    task_outcome: str = Field(
        description=(
            "One-sentence summary of what the agent achieved or failed to achieve."
        )
    )
    success: bool = Field(
        description="True if the agent's response satisfies the expected outcome."
    )
    reasoning_quality_score: float = Field(
        ge=0.0,
        le=10.0,
        description=(
            "0-10 score reflecting the quality and rigour of the agent's reasoning "
            "process (not just the correctness of the final answer)."
        ),
    )
    failure_modes: list[str] = Field(
        description=(
            "Specific failure modes observed in the response. "
            "Empty list if the task was successfully completed."
        )
    )
    instruction_delta: str = Field(
        description=(
            "A concise, actionable instruction to prepend to the system prompt for "
            "future tasks in this category.  Phrased as imperative directives, e.g. "
            "'When solving X, always: 1. ... 2. ...'.  If the task succeeded, "
            "propose a reinforcement instruction to maintain performance."
        )
    )


# ---------------------------------------------------------------------------
# MetacognitiveLog — one complete observe → evaluate → reflect → update cycle
# ---------------------------------------------------------------------------

@dataclass
class MetacognitiveLog:
    """
    Structured record of a single metacognitive cycle (AC #4).
    Serialisable to JSON for offline analysis.
    """
    cycle_id: str
    task_id: str
    task_category: str
    timestamp: datetime

    # Observe phase
    agent_response_preview: str    # first 300 chars of the full response
    agent_success: bool
    injected_delta: Optional[str]  # delta that was active for this run

    # Evaluate phase
    report: SelfEvaluationReport

    # Reflect phase
    previous_delta: Optional[str]  # delta before this evaluation
    delta_changed: bool             # whether the delta was updated

    # Update phase
    new_delta: str                  # delta stored for next task in category

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "task_id": self.task_id,
            "task_category": self.task_category,
            "timestamp": self.timestamp.isoformat(),
            "phase_observe": {
                "agent_response_preview": self.agent_response_preview,
                "agent_success": self.agent_success,
                "injected_delta": self.injected_delta,
            },
            "phase_evaluate": self.report.model_dump(),
            "phase_reflect": {
                "previous_delta": self.previous_delta,
                "delta_changed": self.delta_changed,
            },
            "phase_update": {
                "new_delta": self.new_delta,
            },
        }


# ---------------------------------------------------------------------------
# TaskResult — side-by-side outcome for one task
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    task: Task
    baseline_success: bool
    meta_success: bool
    baseline_response: str
    meta_response: str
    meta_injected_delta: Optional[str]   # delta the meta agent had at run time
    meta_log: Optional[MetacognitiveLog]  # full cycle log for the meta run


# ---------------------------------------------------------------------------
# ComparisonReport — final artefact written to results/
# ---------------------------------------------------------------------------

@dataclass
class ComparisonReport:
    total_tasks: int
    baseline_successes: int
    meta_successes: int
    baseline_success_rate: float
    meta_success_rate: float
    improvement_pp: float            # percentage-point improvement
    task_results: list[TaskResult]
    metacognitive_logs: list[MetacognitiveLog]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "metadata": {
                "timestamp": self.timestamp.isoformat(),
                "poc_author": "Eduardo Arana",
                "project": "agent-metacognition",
                "description": (
                    "POC applying Meta Cognition to AI agents for self-evolution "
                    "and self-evaluation using the Claude SDK."
                ),
            },
            "summary": {
                "total_tasks": self.total_tasks,
                "baseline_success_rate": round(self.baseline_success_rate, 4),
                "meta_success_rate": round(self.meta_success_rate, 4),
                "improvement_percentage_points": round(self.improvement_pp, 2),
                "baseline_successes": self.baseline_successes,
                "meta_successes": self.meta_successes,
            },
            "per_task": [
                {
                    "task_id": r.task.id,
                    "category": r.task.category,
                    "title": r.task.title,
                    "difficulty": r.task.difficulty,
                    "baseline_success": r.baseline_success,
                    "meta_success": r.meta_success,
                    "meta_injected_delta": r.meta_injected_delta,
                }
                for r in self.task_results
            ],
            "metacognitive_cycles": [
                log.to_dict() for log in self.metacognitive_logs
            ],
        }
