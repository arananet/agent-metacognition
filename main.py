#!/usr/bin/env python3
"""
Agent Meta Cognition — POC CLI  (AC #5)

Usage:
    python main.py --mode compare --tasks tasks/general.yaml

Author: Eduardo Arana
Project: agent-metacognition
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.agent import BaselineAgent
from src.evaluator import MetacognitiveEvaluator
from src.logger import CycleLogger
from src.meta_agent import MetaAgent
from src.models import ComparisonReport, Task, TaskResult

console = Console()


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks(path: str) -> list[Task]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    tasks = []
    for t in data.get("tasks", []):
        tasks.append(
            Task(
                id=t["id"],
                category=t["category"],
                title=t["title"],
                prompt=t["prompt"].strip(),
                expected_outcome=t["expected_outcome"].strip(),
                difficulty=t.get("difficulty", "medium"),
                tags=t.get("tags", []),
            )
        )
    return tasks


# ---------------------------------------------------------------------------
# Compare mode  (AC #5 — the primary CLI surface)
# ---------------------------------------------------------------------------

def run_compare(tasks: list[Task], output_dir: Path) -> None:
    """
    Run both agents on every task, log metacognitive cycles, print a
    side-by-side comparison table, and write a JSON report to output_dir/.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[bold red]ERROR:[/bold red] ANTHROPIC_API_KEY environment variable not set."
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Timestamp used for file names
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    cycles_path = output_dir / f"cycles_{ts}.jsonl"
    report_path = output_dir / f"comparison_{ts}.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_agent = BaselineAgent(client)
    evaluator = MetacognitiveEvaluator(client)

    with CycleLogger(cycles_path) as logger:
        meta_agent = MetaAgent(client, logger)

        task_results: list[TaskResult] = []
        logs = []

        console.print(
            Panel(
                "[bold cyan]Agent Meta Cognition POC[/bold cyan]\n"
                f"Tasks: {len(tasks)}   Model: claude-opus-4-6\n"
                "Author: Eduardo Arana",
                title="[bold]Starting comparison run[/bold]",
                expand=False,
            )
        )

        for idx, task in enumerate(tasks, 1):
            console.rule(
                f"[bold white]Task {idx}/{len(tasks)}: "
                f"[cyan]{task.id}[/cyan] — {task.title}[/bold white]"
            )

            # ── Baseline ──────────────────────────────────────────────
            console.print(f"  [yellow]→[/yellow] Running [bold]baseline[/bold] agent …")
            baseline_run = baseline_agent.run(task)
            baseline_report = evaluator.evaluate(task, baseline_run)
            baseline_run.success = baseline_report.success

            status_b = "[green]✓[/green]" if baseline_run.success else "[red]✗[/red]"
            console.print(
                f"    Baseline: {status_b}  "
                f"quality={baseline_report.reasoning_quality_score:.1f}/10"
            )

            # ── Meta agent ────────────────────────────────────────────
            active_delta = meta_agent.current_delta(task.category)
            console.print(
                f"  [yellow]→[/yellow] Running [bold]meta[/bold] agent "
                + (f"[dim](delta active)[/dim]" if active_delta else "[dim](no delta yet)[/dim]")
                + " …"
            )
            meta_run = meta_agent.run(task)

            status_m = "[green]✓[/green]" if meta_run.success else "[red]✗[/red]"
            console.print(
                f"    Meta:     {status_m}"
            )

            # Retrieve the log entry the meta agent just appended
            last_log = logger._count  # noqa: SLF001  — internal index for retrieval

            task_results.append(
                TaskResult(
                    task=task,
                    baseline_success=baseline_run.success,
                    meta_success=meta_run.success,
                    baseline_response=baseline_run.response,
                    meta_response=meta_run.response,
                    meta_injected_delta=meta_run.injected_delta,
                    meta_log=None,   # populated from logger below
                )
            )

        # Collect all cycle logs from the logger file for the report
        meta_logs = _read_logs(cycles_path)
        # Attach logs back to task results
        log_by_task = {log.task_id: log for log in meta_logs}
        for tr in task_results:
            tr.meta_log = log_by_task.get(tr.task.id)

    # ── Compute summary stats ─────────────────────────────────────────────
    n = len(task_results)
    b_ok = sum(r.baseline_success for r in task_results)
    m_ok = sum(r.meta_success for r in task_results)
    b_rate = b_ok / n if n else 0.0
    m_rate = m_ok / n if n else 0.0
    improvement_pp = (m_rate - b_rate) * 100

    report = ComparisonReport(
        total_tasks=n,
        baseline_successes=b_ok,
        meta_successes=m_ok,
        baseline_success_rate=b_rate,
        meta_success_rate=m_rate,
        improvement_pp=improvement_pp,
        task_results=task_results,
        metacognitive_logs=meta_logs,
    )

    # ── Print comparison table  (AC #5) ──────────────────────────────────
    _print_table(task_results, report)

    # ── Write JSON report  (AC #5) ────────────────────────────────────────
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

    console.print(
        f"\n[bold green]JSON report written to:[/bold green] {report_path}"
    )
    console.print(
        f"[bold green]Cycle log written to:[/bold green]  {cycles_path}"
    )


# ---------------------------------------------------------------------------
# Rich table display
# ---------------------------------------------------------------------------

def _print_table(results: list[TaskResult], report: ComparisonReport) -> None:
    table = Table(
        title="[bold cyan]Meta Cognition POC — Task Comparison[/bold cyan]",
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )

    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Category", style="magenta")
    table.add_column("Title", style="white")
    table.add_column("Diff.", justify="center")
    table.add_column("Baseline", justify="center")
    table.add_column("Meta", justify="center")
    table.add_column("Delta active?", justify="center")

    for r in results:
        diff_colour = {"easy": "green", "medium": "yellow", "hard": "red"}.get(
            r.task.difficulty, "white"
        )
        table.add_row(
            r.task.id,
            r.task.category,
            r.task.title,
            f"[{diff_colour}]{r.task.difficulty}[/{diff_colour}]",
            "[bold green]✓[/bold green]" if r.baseline_success else "[bold red]✗[/bold red]",
            "[bold green]✓[/bold green]" if r.meta_success else "[bold red]✗[/bold red]",
            "[dim]yes[/dim]" if r.meta_injected_delta else "[dim]—[/dim]",
        )

    console.print()
    console.print(table)

    # Summary panel
    improvement_colour = "green" if report.improvement_pp >= 0 else "red"
    sign = "+" if report.improvement_pp >= 0 else ""
    console.print(
        Panel(
            f"[white]Total tasks:[/white]  [bold]{report.total_tasks}[/bold]\n"
            f"[white]Baseline:[/white]     [bold]{report.baseline_successes}/{report.total_tasks}[/bold]"
            f"  ({report.baseline_success_rate * 100:.1f} %)\n"
            f"[white]Meta:[/white]         [bold]{report.meta_successes}/{report.total_tasks}[/bold]"
            f"  ({report.meta_success_rate * 100:.1f} %)\n"
            f"[white]Improvement:[/white]  "
            f"[bold {improvement_colour}]{sign}{report.improvement_pp:.1f} pp[/bold {improvement_colour}]",
            title="[bold]Summary[/bold]",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# Log reading helper
# ---------------------------------------------------------------------------

def _read_logs(path: Path):
    """Read MetacognitiveLog entries back from the JSONL file for the report."""
    from src.models import MetacognitiveLog, SelfEvaluationReport

    logs = []
    if not path.exists():
        return logs
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                report = SelfEvaluationReport(**d["phase_evaluate"])
                log = MetacognitiveLog(
                    cycle_id=d["cycle_id"],
                    task_id=d["task_id"],
                    task_category=d["task_category"],
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                    agent_response_preview=d["phase_observe"]["agent_response_preview"],
                    agent_success=d["phase_observe"]["agent_success"],
                    injected_delta=d["phase_observe"]["injected_delta"],
                    report=report,
                    previous_delta=d["phase_reflect"]["previous_delta"],
                    delta_changed=d["phase_reflect"]["delta_changed"],
                    new_delta=d["phase_update"]["new_delta"],
                )
                logs.append(log)
            except Exception:
                pass   # malformed line — skip
    return logs


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Agent Meta Cognition POC — apply metacognitive self-evaluation to "
            "a Claude-powered agent and measure performance improvement."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["compare"],
        required=True,
        help="Run mode.  'compare' executes both agents on the task set.",
    )
    parser.add_argument(
        "--tasks",
        required=True,
        metavar="FILE",
        help="Path to a YAML task file (e.g. tasks/general.yaml).",
    )
    parser.add_argument(
        "--output",
        default="results",
        metavar="DIR",
        help="Directory to write JSON report and cycle log (default: results/).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    tasks = load_tasks(args.tasks)
    if not tasks:
        console.print("[bold red]No tasks found in the file.[/bold red]")
        sys.exit(1)

    output_dir = Path(args.output)

    if args.mode == "compare":
        run_compare(tasks, output_dir)


if __name__ == "__main__":
    main()
